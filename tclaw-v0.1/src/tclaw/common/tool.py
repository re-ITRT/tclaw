"""Tool 基类 —— 所有工具的核心抽象。

每个工具独占一个文件夹，包含两样东西：
  - __init__.py       ：代码 + 参数 schema
  - TOOL.md           ：对 LLM 的自然语言描述（ContextManager 注入 system prompt）

两者在同一文件夹，方便开发和分享。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_bus import EventBus
    from .events import Event

from .events import Topics


class Tool(ABC):
    """所有工具的基类。"""

    tool_id: str = ""

    # LLM 函数调用用的参数 schema（OpenAI function-calling 格式）
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    # ── topic 自动派生 ────────────────────────────────────
    @property
    def topics(self) -> list[str]:
        return [f"{Topics.TOOL_INVOKE}.{self.tool_id}"]

    # ── TOOL.md 内容（延迟加载） ──────────────────────────
    _tool_dir: str = ""  # 在 __init__ 中设置
    _tool_md_cache: str | None = None

    @property
    def tool_md(self) -> str:
        """读取同目录下的 TOOL.md。"""
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
        self._bus = bus
        import sys
        mod = sys.modules.get(type(self).__module__)
        self._tool_dir = os.path.dirname(mod.__file__) if mod and mod.__file__ else ""
        self._bus.register_tool(self)

    # ── 工具规格（供 ContextManager / LLM 使用） ─────────

    def get_tool_spec(self) -> dict[str, Any]:
        """OpenAI function-calling 格式的工具定义。
        description 取自 TOOL.md（取第一段或截取前 200 字符）。
        """
        md = self.tool_md.strip()
        if md:
            # 跳过标题行，取第一个非空段作为描述
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

    # ── 子类实现 ───────────────────────────────────────────

    @abstractmethod
    async def handle_event(self, event: Event) -> None:
        ...

    async def publish(self, event: Event) -> None:
        await self._bus.publish(event)
