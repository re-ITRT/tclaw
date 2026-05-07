"""tclaw EventBus —— 事件总线核心。

完整流水线：
- 普通事件：路由到已注册的 handler
- AGENT_MESSAGE_INCOMING / AGENT_TOOL_RESULT：走完整 LLM 循环
  → ContextManager 构建上下文 → LLM → 调 tool 或回复
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, Callable, Coroutine, TYPE_CHECKING

from .events import Event, Topics

from .context_manager import ContextManager

if TYPE_CHECKING:
    from .tool import Tool
    from .llm_client import LLMClient

logger = logging.getLogger("tclaw.event_bus")

Handler = Callable[[Event], Coroutine[Any, Any, None]]

# ── LLM 循环要处理的事件类型 ───────────────────────────────
_LLM_LOOP_TOPICS = {Topics.AGENT_MESSAGE_INCOMING, Topics.AGENT_TOOL_RESULT}


class EventBus:
    """基于 asyncio 的事件总线，按 session 分队列。"""

    def __init__(self) -> None:
        # ── 订阅表 ────────────────────────────────────────
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

        # ── 已注册的工具 ───────────────────────────────────
        self._tools: dict[str, Tool] = {}

        # ── 核心组件 ──────────────────────────────────────
        self._llm: LLMClient | None = None

        # 每个 session 独立的上下文管理器
        self._global_context_mgr: ContextManager | None = None  # 模板
        self._session_context_mgrs: dict[str, ContextManager] = {}

        # ── 按 session 分队列 ──────────────────────────────
        self._session_queues: dict[str, asyncio.Queue[Event]] = {}
        self._worker_tasks: dict[str, asyncio.Task] = {}
        self._dispatcher_task: asyncio.Task | None = None
        self._running = False

    # ── 工具注册 ───────────────────────────────────────────

    def register_tool(self, tool: Tool) -> None:
        self._tools[tool.tool_id] = tool
        for topic in tool.topics:
            self.subscribe(topic, tool.handle_event)
        logger.info("tool registered: %s (topic=%s)", tool.tool_id, tool.topics)

    def unregister_tool(self, tool: Tool) -> None:
        self._tools.pop(tool.tool_id, None)
        for topic in tool.topics:
            self.unsubscribe(topic, tool.handle_event)
        logger.info("tool unregistered: %s", tool.tool_id)

    def load_all_tools(self, tool_classes: list[type[Tool]]) -> None:
        for cls in tool_classes:
            cls(self)

    def reload_user_tools(self, tools_dir: str) -> list[str]:
        """热加载 ~/tclaw/tools/ 下的用户工具。

        扫描 tools_dir 下的子目录，导入并注册每个子目录中的 Tool 子类。
        已有工具不会重复注册（同 tool_id 跳过）。
        返回新注册的工具 ID 列表。
        """
        import importlib, sys
        from ..common.tool import Tool as _ToolBase

        new_ids: list[str] = []

        if not os.path.isdir(tools_dir):
            return new_ids

        sys.path.insert(0, tools_dir)
        try:
            for name in sorted(os.listdir(tools_dir)):
                init_path = os.path.join(tools_dir, name, "__init__.py")
                if not os.path.isfile(init_path):
                    continue
                try:
                    mod = importlib.import_module(name)
                except Exception:
                    continue
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if not (isinstance(obj, type) and issubclass(obj, _ToolBase)
                            and obj is not _ToolBase):
                        continue
                    if obj.tool_id in self._tools:
                        continue
                    obj(self)
                    new_ids.append(obj.tool_id)
        finally:
            sys.path.pop(0)

        return new_ids

    # ── 核心组件 ───────────────────────────────────────────

    @property
    def llm(self) -> LLMClient | None:
        return self._llm

    def set_llm(self, client: LLMClient) -> None:
        self._llm = client

    def set_context_manager(self, mgr: ContextManager) -> None:
        """设置默认上下文管理器（作为新 session 的模板）。"""
        self._global_context_mgr = mgr

    def _get_context_mgr(self, session_id: str) -> ContextManager | None:
        """获取 session 的上下文管理器，不存在则从模板创建。"""
        if session_id in self._session_context_mgrs:
            return self._session_context_mgrs[session_id]
        if self._global_context_mgr is None:
            return None
        # 为 session 创建独立的上下文管理器
        mgr = ContextManager(system_prompt=self._global_context_mgr._system_prompt)
        self._session_context_mgrs[session_id] = mgr
        return mgr

    # ── 订阅 / 取消 ───────────────────────────────────────

    def subscribe(self, topic: str, handler: Handler) -> None:
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        self._subscribers[topic] = [
            h for h in self._subscribers[topic] if h is not handler
        ]

    # ── 发布 ───────────────────────────────────────────────

    async def publish(self, event: Event) -> None:
        sid = event.session_id or "__default__"
        if sid not in self._session_queues:
            self._session_queues[sid] = asyncio.Queue()
            if self._running and sid not in self._worker_tasks:
                self._worker_tasks[sid] = asyncio.create_task(
                    self._session_worker(sid)
                )
        await self._session_queues[sid].put(event)

    # ── 生命周期 ───────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())
        logger.info("event bus started")

    async def stop(self) -> None:
        self._running = False
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks.values(), return_exceptions=True)
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        self._session_queues.clear()
        self._worker_tasks.clear()
        logger.info("event bus stopped")

    # ── 调度器 ─────────────────────────────────────────────

    async def _dispatcher_loop(self) -> None:
        while self._running:
            await asyncio.sleep(0.5)

    async def _session_worker(self, session_id: str) -> None:
        """单个 session 的事件处理协程 —— 串行 FIFO。

        对 LLM 循环事件（AGENT_MESSAGE_INCOMING / AGENT_TOOL_RESULT），
        直接走完整流水线。其余事件路由到各自 handler。
        """
        queue = self._session_queues.get(session_id)

        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if queue.empty() and not self._running:
                    break
                continue

            if event.topic in _LLM_LOOP_TOPICS:
                await self._run_llm_loop(event)
            else:
                await self._route_to_handlers(event)

        self._session_queues.pop(session_id, None)
        self._session_context_mgrs.pop(session_id, None)
        self._worker_tasks.pop(session_id, None)

    # ── LLM 循环 ──────────────────────────────────────────

    def _collect_tool_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for t in self._tools.values():
            specs.append(t.get_tool_spec())
        return specs

    async def _run_llm_loop(self, event: Event) -> None:
        """完整流水线：构建上下文 → LLM → 调 tool 或回复。"""
        llm = self._llm
        ctx = self._get_context_mgr(event.session_id)
        if not llm or not ctx:
            return

        tool_specs = self._collect_tool_specs()

        if event.topic == Topics.AGENT_MESSAGE_INCOMING:
            context = await ctx.build_context(
                new_event={
                    "role": "user",
                    "content": event.payload.get("text", ""),
                    "file_path": event.payload.get("file_path", []),
                    "from_session_id": event.payload.get("from_session_id", ""),
                },
                tool_specs=tool_specs,
            )
        else:
            context = await ctx.build_context(
                tool_result=event.payload,
                tool_specs=tool_specs,
            )

        # ── LLM 推理 ─────────────────────────────────
        response = await llm.chat(context.messages, tools=context.tools)

        # ── 记录历史 ─────────────────────────────────
        if response.text:
            await ctx.append({"role": "assistant", "content": response.text})

        # ── 决定下一步 ───────────────────────────────
        tool_name = response.tool_call['name']

        await self.publish(Event(
            topic=f"{Topics.TOOL_INVOKE}.{tool_name}",
            payload=response.tool_call.get("args", {}),
            source="agent_loop",
            session_id=event.session_id,
        ))

    # ── 普通事件路由 ──────────────────────────────────────

    async def _route_to_handlers(self, event: Event) -> None:
        handlers = self._subscribers.get(event.topic, [])
        if not handlers:
            logger.warning("no handler for topic=%s", event.topic)
            return
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "handler %s failed for event topic=%s",
                    handler.__name__, event.topic,
                )
