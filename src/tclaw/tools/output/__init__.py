"""OutputTool —— 输出给用户（text/figure）或结束会话（end）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class OutputTool(Tool):
    tool_id = "output"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["text", "figure", "end"],
                "description": "text=纯文本，figure=图片，end=结束会话",
            },
            "text": {"type": "string", "description": "mode=text/end 时输出的内容"},
            "path": {"type": "string", "description": "mode=figure 时图片路径"},
        },
        "required": ["mode"],
    }

    async def do_execute(self, payload: dict) -> None:
        mode = payload.get("mode", "text")
        sid = payload.get("session_id", "")

        if mode == "text":
            await self.send_to_frontend(sid, {
                "type": "assistant", "content": payload.get("text", ""),
            })
        elif mode == "figure":
            await self.send_to_frontend(sid, {
                "type": "assistant", "mode": "figure", "path": payload.get("path", ""),
            })
        elif mode == "end":
            return

        await self.reply_to_llm({"status": "done", "mode": mode}, sid)

    async def _on_invoke(self, event: dict) -> None:
        """Output 工具的 tool_start/tool_result 不推前端，避免冗余。"""
        payload = event.get("payload", {})
        sid = payload.get("session_id") or event.get("session_id", "")
        if not payload.get("session_id"):
            payload["session_id"] = sid
        # 直接走 execute 管道，跳过 _on_invoke 的 tool_start/tool_result
        await self.execute(payload)
