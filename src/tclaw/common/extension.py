"""Extension 基类 —— 系统扩展 / 钩子 / 中间件。

跟 Tool 不同：不暴露给 LLM，没有 TOOL.md，没有 function-calling。
但共用 Executable.execute() 执行管道，也有 before/after 生命周期。

用法
----
    class AuditExtension(Extension):
        ext_id = "audit"

        def __init__(self, bus):
            super().__init__(bus)
            # 订阅 exec 工具的 after 事件
            bus.subscribe("tool.invoke.exec:after", self._on_exec)

        async def _on_exec(self, event: dict):
            cmd = event["payload"].get("command", "")
            print(f"[audit] exec: {cmd}")
"""

from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_bus import EventBus

from .executable import Executable


class Extension(Executable, ABC):
    """系统扩展基类。继承 execute() 管道但通常不直接触发。"""

    ext_id: str = ""

    def get_topic(self) -> str:
        return f"extension.{self.ext_id}"

    def get_name(self) -> str:
        return self.ext_id

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._bus.register_extension(self)

    async def do_execute(self, payload: dict) -> None:
        """扩展默认 do_execute 为空——扩展通常通过事件订阅触发。

        如果扩展需要独立的 execute() 管道，重写此方法即可。
        """
        pass
