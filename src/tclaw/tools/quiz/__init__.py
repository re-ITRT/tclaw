"""QuizTool —— 选择题交互组件。

两种模式：
  - blocking（默认）：必须选了才能继续，当前用户消息被阻塞
  - non_blocking：组件挂着，用户可继续聊天，选了直接触发 LLM
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...common.tool import Tool
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class QuizTool(Tool):
    tool_id = "quiz"

    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "题目，如「以下哪个是 Python 的包管理器？」",
            },
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "选项文本"},
                        "value": {"type": "string", "description": "选项值"},
                    },
                    "required": ["label", "value"],
                },
                "description": "选项列表，2-6 个",
            },
            "mode": {
                "type": "string",
                "enum": ["non_blocking", "blocking"],
                "description": "non_blocking=挂着等选（默认，用户可继续聊天），blocking=必须选了再继续",
            },
        },
        "required": ["question", "options"],
    }

    async def do_execute(self, payload: dict) -> None:
        question = payload.get("question", "")
        options = payload.get("options", [])
        mode = payload.get("mode", "non_blocking")

        cid = await self.register_component(
            session_id=payload.get("session_id", ""),
            schema={
                "type": "custom",
                "display": "inline",
                "closable": True,
                "initial_data": {
                    "question": question,
                    "options": options,
                },
            },
        )

        if mode == "blocking":
            # blocking：等用户选完再继续
            result = await self.wait_for_component(cid)
            if result.get("event") == "dismiss":
                ctx = self._bus._get_context_mgr(payload.get("session_id", ""))
                if ctx:
                    ctx.add_to_prelude("system",
                        "## 用户选择题结果\n\n用户关闭了选择题，未做选择。")
                await self.reply_to_llm({
                    "dismissed": True, "question": question,
                }, payload.get("session_id", ""))
                return
            selected = result.get("data", {})
            await self.destroy_component(cid)
            await self.reply_to_llm({
                "question": question,
                "selected": selected.get("value", ""),
                "label": selected.get("label", ""),
            }, payload.get("session_id", ""))
        else:
            # non_blocking：挂了组件就返回，用户慢慢选
            await self.reply_to_llm({
                "status": "showing",
                "component_id": cid,
                "question": question,
                "message": "选择题已展示在对话中，选完自动通知。",
            }, payload.get("session_id", ""))

    async def handle_gateway_event(self, data: dict, session_id: str) -> None:
        """用户选了选项后，前端直接回调此方法。"""
        component_id = data.get("_component_id", "")
        selected = data.get("data", {})
        event_type = data.get("event", "")

        if event_type == "dismiss":
            await self.destroy_component(component_id)
            # 关闭也算一个选择结果，通知 LLM
            ctx = self._bus._get_context_mgr(session_id)
            if ctx:
                ctx.add_to_prelude("system",
                    "## 用户选择题结果\n\n用户关闭了选择题，未做选择。")
            await self.publish({
                "topic": Topics.AGENT_MESSAGE_INCOMING,
                "payload": {
                    "text": "[用户取消了选择]",
                    "from_session_id": session_id,
                },
                "session_id": session_id,
            })
            return

        # 把选择结果注入上下文
        ctx = self._bus._get_context_mgr(session_id)
        if ctx:
            ctx.add_to_prelude("system",
                f"## 用户选择题结果\n\n{selected.get('label', '')}（{selected.get('value', '')}）")

        await self.destroy_component(component_id)

        # 触发 LLM 处理选择结果
        await self.publish({
            "topic": Topics.AGENT_MESSAGE_INCOMING,
            "payload": {
                "text": f"[用户选择：{selected.get('label', '')}]",
                "from_session_id": session_id,
            },
            "session_id": session_id,
        })
