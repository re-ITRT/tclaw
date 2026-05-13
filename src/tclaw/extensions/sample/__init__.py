"""SampleExtension —— 演示扩展系统。

订阅 tool.invoke.exec:after，记录执行命令到日志。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...common.extension import Extension

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.extensions.sample")


class SampleExtension(Extension):
    ext_id = "sample"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        bus.subscribe("tool.invoke.exec:after", self._on_exec)
        logger.info("sample extension hooks active")

    async def _on_exec(self, event: dict) -> None:
        payload = event.get("payload", {})
        cmd = payload.get("command", "")
        sid = payload.get("session_id", "")
        logger.info("[sample hook] session=%s exec=%s", sid, cmd[:100])
