"""CrossSessionTool —— 跨 session 通信。

LLM 通过此工具向其他 session 发送消息，对方会收到并触发 LLM 处理。
非阻塞：发完即回，不等对方回复。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class CrossSessionTool(Tool):
    tool_id = "cross_session"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "target_session": {
                "type": "string",
                "description": "目标 session ID，如 main、sub:my-project、my-agent",
            },
            "content": {
                "type": "string",
                "description": "要发送的消息内容",
            },
        },
        "required": ["target_session", "content"],
    }

    async def do_execute(self, payload: dict) -> None:
        target = payload.get("target_session", "")
        content = payload.get("content", "")
        sender = payload.get("session_id", "main")

        if not target or not content:
            await self.reply_to_llm({
                "status": "error",
                "message": "target_session and content required",
            }, sender)
            return

        # 构造给对方的消息
        event = {
            "topic": Topics.AGENT_MESSAGE_INCOMING,
            "payload": {
                "text": content,
                "from_session_id": sender,
            },
            "session_id": target,
        }

        try:
            await self._bus.publish(event)
            await self.reply_to_llm({
                "status": "ok",
                "message": f"消息已发送到 {target}",
                "target_session": target,
            }, sender)
        except Exception as e:
            await self.reply_to_llm({
                "status": "error",
                "message": f"发送失败: {e}",
            }, sender)
