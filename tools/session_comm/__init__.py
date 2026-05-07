"""SessionCommTool —— 跨 session 通信。

通过 session_id 向另一个 session 发送消息，实现 session 间的交流。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tclaw.common.tool import Tool
from tclaw.common.events import Event, Topics

if TYPE_CHECKING:
    from tclaw.common.event_bus import EventBus


class SessionCommTool(Tool):
    tool_id = "session_comm"
    parameters = {
        "type": "object",
        "properties": {
            "to_session_id": {
                "type": "string",
                "description": "目标 session 的 ID",
            },
            "message": {
                "type": "string",
                "description": "要发送的消息内容",
            },
        },
        "required": ["to_session_id", "message"],
    }

    async def handle_event(self, event: Event) -> None:
        to_sid = event.payload.get("to_session_id", "")
        message = event.payload.get("message", "")

        if not to_sid or not message:
            return

        # 以 AGENT_MESSAGE_INCOMING 发往目标 session
        # 来源与文字内容分开，ContextManager 自行拼接
        await self.publish(Event(
            topic=Topics.AGENT_MESSAGE_INCOMING,
            payload={
                "text": message,
                "from_session_id": event.session_id,
            },
            source=self.tool_id,
            session_id=to_sid,
        ))

        # 告知调用方已发送
        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={
                "tool": "session_comm",
                "status": "sent",
                "to_session_id": to_sid,
            },
            source=self.tool_id,
            session_id=event.session_id,
        ))
