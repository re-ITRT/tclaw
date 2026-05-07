"""CompactTool —— 压缩对话上下文，释放 Token 空间。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class CompactTool(Tool):
    tool_id = "compact"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def handle_event(self, event: Event) -> None:
        llm = self._bus.llm
        ctx = self._bus._get_context_mgr(event.session_id)
        if not llm or not ctx:
            return

        summary = await ctx.compact(llm)

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={
                "tool": "compact",
                "status": "done",
                "summary": summary,
            },
            source=self.tool_id,
            session_id=event.session_id,
        ))
