"""EditTool —— 文件编辑（精确替换）。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.settings import resolve_path
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class EditTool(Tool):
    tool_id = "edit"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径。相对路径以工作区为根，绝对路径直接使用"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "oldText": {"type": "string", "description": "要被替换的精确文本"},
                        "newText": {"type": "string", "description": "替换后的文本"},
                    },
                    "required": ["oldText", "newText"],
                },
                "description": "替换操作列表",
            },
        },
        "required": ["path", "edits"],
    }

    async def do_execute(self, payload: dict) -> None:
        p = payload
        path, edits = p.get("path", ""), p.get("edits", [])
        if not path:
            return await self._result(payload, {"status": "error", "error": "path required"})
        if not edits:
            return await self._result(payload, {"status": "error", "error": "edits required"})
        ap = resolve_path(path)
        if not os.path.exists(ap):
            return await self._result(payload, {"status": "error", "error": f"Not found: {path}"})
        try:
            with open(ap, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return await self._result(payload, {"status": "error", "error": str(e)})
        norm = content.replace("\r\n", "\n").replace("\r", "\n")
        for e in edits:
            old = e.get("oldText", "").replace("\r\n", "\n").replace("\r", "\n")
            new = e.get("newText", "")
            if not old or old.strip() == "":
                continue
            count = norm.count(old)
            if count == 0:
                return await self._result(payload, {"status": "error",
                    "error": f"Could not find exact text in {path}.\nFile:\n{content[:800]}"})
            if count > 1:
                return await self._result(payload, {"status": "error",
                    "error": f"Found {count} occurrences — must be unique"})
            norm = norm.replace(old, new, 1)
        try:
            with open(ap, "w", encoding="utf-8") as f:
                f.write(norm)
        except Exception as e:
            return await self._result(payload, {"status": "error", "error": str(e)})
        msg = f"Successfully replaced {len(edits)} block(s) in {path}." if len(edits) > 1 else f"Successfully replaced text in {path}."
        await self._result(payload, {"status": "done", "path": ap, "edits_applied": len(edits), "message": msg})

    async def _result(self, _, payload):
        await self.reply_to_llm(payload, payload.get("session_id", ""))
