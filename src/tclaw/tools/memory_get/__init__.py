"""MemoryGetTool —— 读取记忆文件。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics
from ...common.settings import MEMORY_DIR

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class MemoryGetTool(Tool):
    tool_id = "memory_get"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "记忆文件路径（相对于 memory/，如 MEMORY.md、daily/2026-05-07.md）",
            },
            "offset": {
                "type": "integer",
                "description": "起始行号（1-indexed，默认 1）",
            },
            "limit": {
                "type": "integer",
                "description": "最大行数（默认 200）",
            },
        },
        "required": ["path"],
    }

    async def handle_event(self, event: Event) -> None:
        rel_path = event.payload.get("path", "")
        offset = event.payload.get("offset", 1)
        limit = event.payload.get("limit", 200)

        if not rel_path:
            return

        abs_path = os.path.normpath(os.path.join(MEMORY_DIR, rel_path))

        # 安全检查：不能跑到 memory/ 外面
        if not abs_path.startswith(os.path.normpath(MEMORY_DIR)):
            await self.publish(Event(
                topic=Topics.AGENT_TOOL_RESULT,
                payload={"tool": "memory_get", "status": "error",
                         "error": "Path must be under memory/"},
                source=self.tool_id,
                session_id=event.session_id,
            ))
            return

        if not os.path.isfile(abs_path):
            await self.publish(Event(
                topic=Topics.AGENT_TOOL_RESULT,
                payload={"tool": "memory_get", "status": "error",
                         "error": f"Not found: {rel_path}"},
                source=self.tool_id,
                session_id=event.session_id,
            ))
            return

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            await self.publish(Event(
                topic=Topics.AGENT_TOOL_RESULT,
                payload={"tool": "memory_get", "status": "error", "error": str(e)},
                source=self.tool_id,
                session_id=event.session_id,
            ))
            return

        total = len(lines)
        start = max(0, offset - 1)
        end = min(start + limit, total)
        text = "".join(lines[start:end])

        if end < total:
            text += f"\n\n[{total - end} more lines. Use offset={end + 1} to continue.]"

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={
                "tool": "memory_get",
                "status": "done",
                "path": rel_path,
                "text": text,
                "total_lines": total,
                "lines_shown": end - start,
            },
            source=self.tool_id,
            session_id=event.session_id,
        ))
