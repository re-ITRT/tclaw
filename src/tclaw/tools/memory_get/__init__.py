"""MemoryGetTool —— 读取记忆文件。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Topics
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
                "description": "记忆文件路径。相对 memory/workspace/memory/ 下，如 MEMORY.md=workspace/memory/MEMORY.md",
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

    async def do_execute(self, payload: dict) -> None:
        rel_path = payload.get("path", "")
        offset = payload.get("offset", 1)
        limit = payload.get("limit", 200)

        if not rel_path:
            return

        abs_path = os.path.normpath(os.path.join(MEMORY_DIR, rel_path))

        if not abs_path.startswith(os.path.normpath(MEMORY_DIR)):
            await self.reply_to_llm({
                "status": "error", "error": "Path must be under memory/",
            }, payload.get("session_id", ""))
            return

        if not os.path.isfile(abs_path):
            await self.reply_to_llm({
                "status": "error", "error": f"Not found: {rel_path}",
            }, payload.get("session_id", ""))
            return

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            await self.reply_to_llm({
                "status": "error", "error": str(e),
            }, payload.get("session_id", ""))
            return

        total = len(lines)
        start = max(0, offset - 1)
        end = min(start + limit, total)
        text = "".join(lines[start:end])

        if end < total:
            text += f"\n\n[{total - end} more lines. Use offset={end + 1} to continue.]"

        await self.reply_to_llm({
            "status": "done",
            "path": rel_path,
            "text": text,
            "total_lines": total,
            "lines_shown": end - start,
        }, payload.get("session_id", ""))
