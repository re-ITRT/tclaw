"""CompactorExtension —— 上下文压缩扩展。

监听 compact 事件，将早期对话历史压缩为摘要，
保留最近的消息，归档原始历史到 logs/sessions/archives/。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...common.extension import Extension

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.extensions.compactor")


class CompactorExtension(Extension):
    """上下文压缩扩展。"""

    ext_id = "compactor"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        bus.subscribe("extension.compactor.compact", self._on_compact)
        logger.info("compactor extension active")

    async def _on_compact(self, event: dict) -> None:
        """收到压缩指令。"""
        payload = event.get("payload", {})
        session_id = payload.get("session_id", "") or event.get("session_id", "")
        keep_recent = payload.get("keep_recent", 20000)
        user_prompt = payload.get("prompt", "")

        ctx = self._bus._get_context_mgr(session_id)
        llm = self._bus.llm
        if not ctx or not llm:
            logger.warning("compact: no context or llm for session=%s", session_id)
            return

        logger.info("compacting session=%s (keep_recent=%d)", session_id, keep_recent)
        try:
            summary = await ctx.compact(llm, keep_recent=keep_recent, user_prompt=user_prompt)
            logger.info("compact done: %d chars summary", len(summary))

            # 通知前端
            await self.send_to_frontend(session_id, {
                "type": "system",
                "content": f"上下文已压缩，摘要 {len(summary)} 字",
            })
        except Exception as e:
            logger.exception("compact failed: %s", e)
            await self.send_to_frontend(session_id, {
                "type": "system",
                "content": f"压缩失败: {e}",
            })
