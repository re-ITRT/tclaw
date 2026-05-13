"""OutputPlugin —— 监听 LLM 输出事件，与 Gateway 交互。

订阅 tool.invoke.output:after，拿到 LLM 的文本回复，
可通过 Gateway 推通知、写日志、或其他操作。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...common.extension import Extension

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.extensions.output_plugin")


class OutputPlugin(Extension):
    """监听 LLM 输出的扩展。

    通过 tool.invoke.output 的 after 事件拿到 LLM 的回复文本，
    可以推额外通知、记录到数据库、或跟其他系统交互。
    """

    ext_id = "output_plugin"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        # 监听 LLM 文本输出的 after 事件
        bus.subscribe("tool.invoke.output:after", self._on_output)
        logger.info("output plugin active")

    async def _on_output(self, event: dict) -> None:
        """LLM 输出文本后触发。"""
        payload = event.get("payload", {})
        text = payload.get("text", "")
        sid = payload.get("session_id", "")

        if not text:
            return

        # 示例：在控制台记录
        logger.info("[output] session=%s text=%s", sid, text[:120])

        # 示例：推额外通知到前端
        # await self.send_to_frontend(sid, {
        #     "type": "system",
        #     "content": f"[output] LLM 回复了 {len(text)} 字",
        # })
