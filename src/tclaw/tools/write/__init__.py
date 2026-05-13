"""WriteTool —— 文件写入。"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.settings import resolve_path
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class WriteTool(Tool):
    tool_id = "write"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径。相对路径以工作区为根，绝对路径直接使用"},
            "content": {"type": "string", "description": "写入的内容"},
            "append": {"type": "boolean", "description": "是否追加（默认 false=覆盖）"},
        },
        "required": ["path", "content"],
    }

    async def do_execute(self, payload: dict) -> None:
        p = payload
        path, content, append = p.get("path", ""), p.get("content", ""), p.get("append", False)
        if not path:
            return await self._result(event, {"status": "error", "error": "path required"})
        ap = resolve_path(path)
        try:
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "a" if append else "w", encoding="utf-8") as f:
                f.write(content)
            await self._result(event, {"status": "done", "path": ap,
                                        "bytes_written": len(content.encode("utf-8")), "append": append})
        except Exception as e:
            await self._result(event, {"status": "error", "error": str(e)})

    async def _result(self, event, payload):
        await self.reply_to_llm(payload, payload.get("session_id", ""))
