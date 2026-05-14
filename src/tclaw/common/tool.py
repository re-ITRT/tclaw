"""Tool 基类 —— LLM 可调用的工具。

每个工具独占一个文件夹：
  - __init__.py       ：代码 + 参数 schema
  - TOOL.md           ：对 LLM 的自然语言描述

执行管道继承自 Executable.execute()：
  tool.invoke.{id}:before → 其他模块可取消
  do_execute()            → 实际干活 + 推前端
  tool.invoke.{id}:after  → 其他模块可响应
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_bus import EventBus

from .events import Topics
from .executable import Executable


class Tool(Executable, ABC):
    """所有工具的基类。通过 Executable.execute(payload) 统一执行。"""

    tool_id: str = ""

    # LLM 函数调用用的参数 schema
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    # ── Executable 接口实现 ──────────────────────────────

    def get_topic(self) -> str:
        return f"{Topics.TOOL_INVOKE}.{self.tool_id}"

    @property
    def topics(self) -> list[str]:
        """EventBus 订阅用的 topic 列表。"""
        return [self.get_topic()]

    def get_name(self) -> str:
        return self.tool_id

    # ── TOOL.md 内容（延迟加载） ──────────────────────────
    _tool_dir: str = ""
    _tool_md_cache: str | None = None

    @property
    def tool_md(self) -> str:
        if self._tool_md_cache is not None:
            return self._tool_md_cache
        md_path = os.path.join(self._tool_dir, "TOOL.md")
        if os.path.isfile(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                self._tool_md_cache = f.read()
        else:
            self._tool_md_cache = ""
        return self._tool_md_cache

    def clear_tool_md_cache(self) -> None:
        self._tool_md_cache = None

    # ── 构造 ───────────────────────────────────────────────

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._gateway = getattr(bus, "_gateway", None)
        import sys
        mod = sys.modules.get(type(self).__module__)
        self._tool_dir = os.path.dirname(mod.__file__) if mod and mod.__file__ else ""
        self._bus.register_tool(self)

    # ── 工具规格（供 ContextManager / LLM 使用） ─────────

    def get_tool_spec(self) -> dict[str, Any]:
        md = self.tool_md.strip()
        if md:
            lines = md.split("\n")
            parts = "\n".join(l for l in lines if not l.startswith("#")).strip().split("\n\n")
            desc = parts[0].strip().replace("\n", " ")[:200] if parts else ""
        else:
            desc = ""
        return {
            "type": "function",
            "function": {
                "name": self.tool_id,
                "description": desc,
                "parameters": self.parameters,
            },
        }

    # ── EventBus 回调 — 提取 payload 传给 execute() ────

    async def _on_invoke(self, event: dict) -> None:
        """EventBus 收到 tool.invoke.{id} 时的入口。"""
        payload = event.get("payload", {})
        sid = payload.get("session_id") or event.get("session_id", "")
        if not payload.get("session_id"):
            payload["session_id"] = sid

        # 通知前端工具开始执行
        await self.send_to_frontend(sid, {
            "type": "tool_start", "tool_id": self.tool_id, "args": payload,
        })

        await self.execute(payload)

        # 通知前端工具执行完毕
        await self.send_to_frontend(sid, {
            "type": "tool_result", "tool_id": self.tool_id, "status": "done",
        })

    # ── 执行 ─────────────────────────────────────────────

    @abstractmethod
    async def do_execute(self, payload: dict) -> None:
        """核心逻辑。由 Executable.execute() 在 before/after 之间调用。"""
        ...

    async def handle_gateway_event(self, data: dict, session_id: str) -> None:
        """从 Gateway 来（前端交互，绕过 LLM）。

        默认行为：直接走 execute() 管道。
        """
        payload = dict(data)
        payload["session_id"] = session_id
        await self.execute(payload)

    # ── 发布事件 ───────────────────────────────────────────

    async def publish(self, event: dict | list) -> None:
        """发布事件到 EventBus。

        event 格式：{"topic": ..., "payload": ..., "session_id": ...}
        """
        await self._bus.publish(event)

    # ── 快捷回复 LLM ───────────────────────────────────────

    async def reply_to_llm(self, payload: dict, session_id: str) -> None:
        payload["tool_id"] = self.tool_id
        await self._bus.publish({
            "topic": Topics.AGENT_TOOL_RESULT,
            "payload": payload,
            "session_id": session_id,
        })
