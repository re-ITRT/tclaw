"""LoadSkillTool —— 按需加载完整 SKILL.md 到上下文。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics
from ...common.skills import load_skill_content, discover_skills

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class LoadSkillTool(Tool):
    tool_id = "load_skill"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "技能名称（与菜单中的 name 一致）",
            },
        },
        "required": ["name"],
    }

    async def handle_event(self, event: Event) -> None:
        skill_name = event.payload.get("name", "")
        if not skill_name:
            return

        content = load_skill_content(skill_name)
        if not content:
            await self.publish(Event(
                topic=Topics.AGENT_TOOL_RESULT,
                payload={
                    "tool": "load_skill", "status": "error",
                    "error": f"Not found: {skill_name}. Available: {', '.join(discover_skills())}",
                },
                source=self.tool_id, session_id=event.session_id,
            ))
            return

        # 直接拿 ContextManager 注入到 prelude
        ctx = self._bus._get_context_mgr(event.session_id)
        if ctx:
            ctx.add_to_prelude("system", f"## 技能：{skill_name}\n\n{content}")

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={"tool": "load_skill", "status": "done", "name": skill_name,
                     "message": f"Skill '{skill_name}' loaded."},
            source=self.tool_id, session_id=event.session_id,
        ))
