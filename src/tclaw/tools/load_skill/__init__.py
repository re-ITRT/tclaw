"""LoadSkillTool —— 按需加载完整 SKILL.md 到上下文。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Topics
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

    async def do_execute(self, payload: dict) -> None:
        skill_name = payload.get("name", "")
        if not skill_name:
            return

        content = load_skill_content(skill_name)
        if not content:
            await self.reply_to_llm({
                "status": "error",
                "error": f"Not found: {skill_name}. Available: {', '.join(discover_skills())}",
            }, payload.get("session_id", ""))
            return

        # 直接拿 ContextManager 注入到 prelude
        ctx = self._bus._get_context_mgr(payload.get("session_id", ""))
        if ctx:
            ctx.add_to_prelude("system", f"## 技能：{skill_name}\n\n{content}")

        await self.reply_to_llm({
            "status": "done", "name": skill_name,
            "content": content,
            "message": f"Skill '{skill_name}' loaded.",
        }, payload.get("session_id", ""))
