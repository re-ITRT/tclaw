"""OutputTool —— 输出给用户（text/figure）或结束会话（end）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics

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

    async def handle_event(self, event: Event) -> None:
        payload = event.payload
        mode = payload.get("mode", "text")
        output = {"mode": mode}

        if mode == "text":
            output["text"] = payload.get("text", "")
        elif mode == "figure":
            output["path"] = payload.get("path", "")
        elif mode == "end":
            output["text"] = payload.get("text", "")

        # 推送输出给前端
        await self.publish(Event(
            topic=Topics.AGENT_OUTPUT, payload=output,
            source=self.tool_id, session_id=event.session_id,
        ))

        if mode == "end":
            # end 模式不发 TOOL_RESULT，LLM 循环自然停止
            return

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={"tool": "output", "status": "done", **output},
            source=self.tool_id, session_id=event.session_id,
        ))
