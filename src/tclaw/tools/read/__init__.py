"""ReadTool —— 文件阅读。"""

from __future__ import annotations

import os, mimetypes
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.settings import resolve_path
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

MAX_LINES = 2000
MAX_BYTES = 50 * 1024
IMAGES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


class ReadTool(Tool):
    tool_id = "read"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径。相对路径以工作区为根，绝对路径直接使用"},
            "offset": {"type": "integer", "description": "起始行号（1-indexed，默认 1）"},
            "limit": {"type": "integer", "description": "最大行数（默认 2000）"},
        },
        "required": ["path"],
    }

    async def do_execute(self, payload: dict) -> None:
        p = payload
        path, offset, limit = p.get("path", ""), p.get("offset", 1), p.get("limit", MAX_LINES)
        if not path:
            return await self._result(payload, {"status": "error", "error": "path required"})
        ap = resolve_path(path)
        if not os.path.exists(ap):
            return await self._result(payload, {"status": "error", "error": f"Not found: {path}"})
        ext = os.path.splitext(ap)[1].lower()
        if ext in IMAGES:
            return await self._handle_image(payload, ap)
        await self._handle_text(payload, ap, offset, limit)

    async def _handle_text(self, args, path, offset, limit):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return await self._result(payload, {"status": "error", "error": str(e)})
        total = len(lines)
        start = max(0, offset - 1); end = min(start + limit, total)
        text = "".join(lines[start:end])
        capped, cont = False, end if end < total else None
        if len(text.encode("utf-8")) > MAX_BYTES:
            text = text.encode("utf-8")[:MAX_BYTES].decode("utf-8", errors="replace")
            capped = True
        notes = []
        if capped:
            notes.append(f"Read output capped at 50KB for this call.")
        if cont and not capped:
            notes.append(f"Showing lines {offset}-{end}. Use offset={cont} to continue.")
        elif cont:
            notes.append(f"Use offset={cont} to continue.")
        if notes:
            text += f"\n\n[{' | '.join(notes)}]"
        await self._result(payload, {"status": "done", "path": path,
                                    "text": text, "total_lines": total,
                                    "lines_shown": end - start, "offset": offset})

    async def _handle_image(self, args, path):
        import base64
        mime = mimetypes.guess_type(path)[0] or "image/png"
        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return await self._result(payload, {"status": "error", "error": str(e)})
        await self._result(payload, {"status": "done", "path": path,
                                    "type": "image", "mime_type": mime, "data": data})

    async def _result(self, _, payload):
        await self.reply_to_llm(payload, payload.get("session_id", ""))
