"""tclaw EventBus —— 事件总线核心。

事件格式：{"topic": str, "payload": dict}
  - topic：路由用
  - payload：所有数据都在这里，约定包含 session_id/source 等

Tool：注册时自动订阅 tool.invoke.{tool_id}，LLM 通过 topic 路由
Extension：自己订阅要监听的事件
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, Callable, Coroutine, TYPE_CHECKING

from .events import Topics
from .conversation_logger import log_assistant
from .context_manager import ContextManager

if TYPE_CHECKING:
    from .tool import Tool
    from .extension import Extension
    from .llm_client import LLMClient

logger = logging.getLogger("tclaw.event_bus")

Handler = Callable[[dict], Coroutine[Any, Any, None]]

_LLM_TRIGGER_TOPICS = {Topics.AGENT_MESSAGE_INCOMING, Topics.AGENT_TOOL_RESULT}


class EventBus:
    """基于 asyncio 的事件总线，按 session 分队列。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._tools: dict[str, Tool] = {}
        self._extensions: dict[str, Extension] = {}
        self._llm: LLMClient | None = None
        self._global_context_mgr: ContextManager | None = None
        self._session_context_mgrs: dict[str, ContextManager] = {}
        self.component_manager: Any = None  # 由 Gateway 注入
        self._gateway: Any = None           # 由 Gateway 注入
        self.frontend_service: Any = None   # 由 Gateway 注入
        self._session_queues: dict[str, asyncio.Queue[dict]] = {}
        self._worker_tasks: dict[str, asyncio.Task] = {}
        self._dispatcher_task: asyncio.Task | None = None
        self._running = False

    # ── Tool 注册 ───────────────────────────────────────────

    def register_tool(self, tool: Tool) -> None:
        self._tools[tool.tool_id] = tool
        for topic in tool.topics:
            self.subscribe(topic, tool._on_invoke)
        logger.info("tool registered: %s (topic=%s)", tool.tool_id, tool.topics)

    def unregister_tool(self, tool: Tool) -> None:
        self._tools.pop(tool.tool_id, None)
        for topic in tool.topics:
            self.unsubscribe(topic, tool._on_invoke)

    @property
    def registered_tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    def get_tool(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def load_all_tools(self, tool_classes: list[type[Tool]]) -> None:
        for cls in tool_classes:
            cls(self)

    def reload_user_tools(self, tools_dir: str) -> list[str]:
        import importlib, sys
        from .tool import Tool as _ToolBase

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

    # ── Extension 注册 ───────────────────────────────────────

    def register_extension(self, ext: Extension) -> None:
        self._extensions[ext.ext_id] = ext
        logger.info("extension registered: %s", ext.ext_id)

    @property
    def registered_extensions(self) -> dict[str, Extension]:
        return dict(self._extensions)

    def get_extension(self, ext_id: str) -> Extension | None:
        return self._extensions.get(ext_id)

    def load_all_extensions(self, ext_classes: list[type[Extension]]) -> None:
        for cls in ext_classes:
            cls(self)

    # ── 核心组件 ───────────────────────────────────────────

    @property
    def llm(self) -> LLMClient | None:
        return self._llm

    def set_llm(self, client: LLMClient) -> None:
        self._llm = client

    def set_context_manager(self, mgr: ContextManager) -> None:
        self._global_context_mgr = mgr

    def _get_context_mgr(self, session_id: str) -> ContextManager | None:
        if session_id in self._session_context_mgrs:
            return self._session_context_mgrs[session_id]
        if self._global_context_mgr is None:
            return None
        mgr = ContextManager(
            system_prompt=self._global_context_mgr._system_prompt,
            session_type="main",
            session_id=session_id,
        )
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

    async def publish(self, event: dict) -> None:
        """发布事件。event = {"topic": ..., "payload": {...}}

        payload 约定包含 session_id、source 等字段。
        """
        if isinstance(event, list):
            for e in event:
                await self.publish(e)
            return

        topic = event.get("topic", "")
        payload = event.get("payload", {})
        # session_id 可能出现在 event 顶层或 payload 里
        sid = payload.get("session_id") or event.get("session_id", "__default__")
        event_with_defaults = dict(event)
        if "session_id" not in event_with_defaults or not event_with_defaults.get("session_id"):
            event_with_defaults["session_id"] = sid
        # 确保 payload 里也有 session_id（下游 tools 从 payload 取）
        if "session_id" not in event_with_defaults.get("payload", {}):
            event_with_defaults.setdefault("payload", {})
            event_with_defaults["payload"]["session_id"] = sid

        if sid not in self._session_queues:
            self._session_queues[sid] = asyncio.Queue()
            if self._running and sid not in self._worker_tasks:
                self._worker_tasks[sid] = asyncio.create_task(
                    self._session_worker(sid)
                )
        await self._session_queues[sid].put(event_with_defaults)

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
        queue = self._session_queues.get(session_id)

        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if queue.empty() and not self._running:
                    break
                continue

            topic = event.get("topic", "")

            if topic in _LLM_TRIGGER_TOPICS:
                if topic == Topics.AGENT_TOOL_RESULT:
                    ctx = self._get_context_mgr(session_id)
                    if ctx:
                        payload = event.get("payload", {})
                        tool_msg = {"role": "tool", "content": str(payload)}
                        if ctx._last_tool_call_ids:
                            tool_msg["tool_call_id"] = ctx._last_tool_call_ids.pop(0)
                        await ctx.append(tool_msg)

                # 有未完成的 tool_calls 时暂缓触发 LLM
                ctx = self._get_context_mgr(session_id)
                if ctx and ctx.history:
                    pending = 0
                    for m in reversed(ctx.history):
                        role = m.get("role", "")
                        if role == "tool":
                            pending -= 1
                        elif role == "assistant" and m.get("tool_calls"):
                            pending += len(m["tool_calls"])
                            if pending > 0:
                                break
                        else:
                            break
                    if pending > 0:
                        if topic == Topics.AGENT_MESSAGE_INCOMING:
                            await queue.put(event)
                            logger.info("deferred: %d pending tool_calls", pending)
                        else:
                            logger.debug("tool result queued, %d still pending", pending)
                        continue

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

    async def _run_llm_loop(self, event: dict) -> None:
        """单次 LLM 推理。"""
        llm = self._llm
        sid = event.get("session_id", "") or event.get("payload", {}).get("session_id", "")
        ctx = self._get_context_mgr(sid)
        if not llm or not ctx:
            return

        tool_specs = self._collect_tool_specs()

        if event.get("topic") == Topics.AGENT_MESSAGE_INCOMING:
            payload = event.get("payload", {})
            context = await ctx.build_context(
                new_event={
                    "role": "user",
                    "content": payload.get("text", ""),
                    "file_path": payload.get("file_path", []),
                    "from_session_id": payload.get("from_session_id", ""),
                },
                tool_specs=tool_specs,
            )
        else:
            context = await ctx.build_context(tool_specs=tool_specs)

        response = await llm.chat(context.messages, tools=context.tools)

        if response.tool_call:
            if response.assistant_message:
                await ctx.append(response.assistant_message)

            display_text = response.text
            if not display_text and response.assistant_message:
                display_text = response.assistant_message.get("reasoning_content", "")
            if display_text and self.frontend_service:
                await self.frontend_service.send(sid, {
                    "type": "assistant", "content": display_text,
                })

            if response.tool_calls:
                for tc in response.tool_calls:
                    ctx._last_tool_call_ids.append(tc.get("id", ""))

            for tc in response.tool_calls:
                tool_name = tc["name"]
                raw_args = tc.get("args", {})
                if isinstance(raw_args, str):
                    import json as _json
                    try:
                        raw_args = _json.loads(raw_args)
                    except _json.JSONDecodeError:
                        raw_args = {"_raw": raw_args}
                await self.publish({
                    "topic": f"{Topics.TOOL_INVOKE}.{tool_name}",
                    "payload": raw_args,
                    "session_id": sid,
                })
        else:
            if response.assistant_message:
                await ctx.append(response.assistant_message)
            if response.text:
                log_assistant(sid, response.text)
                if self.frontend_service:
                    await self.frontend_service.send(sid, {
                        "type": "assistant", "content": response.text,
                    })

    # ── 普通事件路由 ──────────────────────────────────────

    async def _route_to_handlers(self, event: dict) -> None:
        topic = event.get("topic", "")
        handlers = self._subscribers.get(topic, [])
        if not handlers:
            logger.warning("no handler for topic=%s", topic)
            return
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "handler %s failed for event topic=%s",
                    handler.__name__, topic,
                )

    # ── 同步分发（用于 before/after 生命周期） ──────────

    async def dispatch_sync(self, topic: str, payload: dict) -> bool:
        """同步分发事件到所有订阅者（不入队列）。

        订阅者可以修改 payload（如设置 cancelled=True）。
        返回 True 表示事件被取消。
        """
        handlers = self._subscribers.get(topic, [])
        if not handlers:
            return False
        event = {"topic": topic, "payload": payload}
        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception("sync handler failed: %s", handler.__name__)
        return payload.get("cancelled", False)
