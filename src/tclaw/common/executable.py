"""Executable 基类 —— Tool 和 Extension 共用的执行管道。

每个执行都经过统一生命周期：

  execute(payload)
    ├── check cancelled
    ├── publish({topic}:before)  → 订阅者可以取消
    ├── check cancelled
    ├── do_execute(payload)      → 实际逻辑
    └── publish({topic}:after)   → 订阅者做后续处理
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .event_bus import EventBus

logger = logging.getLogger("tclaw.executable")


class Executable(ABC):
    """可执行组件的基类。Tool 和 Extension 共用。"""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._gateway = getattr(bus, "_gateway", None)

    # ── Topic ──────────────────────────────────────────────

    @abstractmethod
    def get_topic(self) -> str:
        """基础 topic，用于构建 before/after。"""
        ...

    def get_before_topic(self) -> str:
        return f"{self.get_topic()}:before"

    def get_after_topic(self) -> str:
        return f"{self.get_topic()}:after"

    # ── 执行管道 ──────────────────────────────────────────

    async def execute(self, payload: dict) -> None:
        """统一执行入口。带 before/after 生命周期。"""
        name = self.get_name()

        # 1. 检查是否已被取消
        if payload.get("cancelled", False):
            logger.debug("[%s] 已被取消，跳过", name)
            return

        # 2. 广播 before 事件（同步分发，订阅者可取消）
        logger.debug("[%s] 广播 before 事件...", name)
        cancelled = await self._bus.dispatch_sync(self.get_before_topic(), payload)
        if cancelled:
            payload["cancelled"] = True
            logger.info("[%s] before 阶段被取消", name)
            return

        # 3. 再次检查
        if payload.get("cancelled", False):
            return

        # 4. 执行核心逻辑
        logger.debug("[%s] 执行核心逻辑...", name)
        await self.do_execute(payload)

        # 5. 广播 after 事件
        logger.debug("[%s] 广播 after 事件...", name)
        await self._bus.dispatch_sync(self.get_after_topic(), payload)

    @abstractmethod
    async def do_execute(self, payload: dict) -> None:
        """子类实现的实际逻辑。"""
        ...

    # ── 辅助 ──────────────────────────────────────────────

    @abstractmethod
    def get_name(self) -> str:
        """人类可读的名称（tool_id / ext_id）。"""
        ...

    # ── 前端通信（Tool 和 Extension 共用） ──────────────────

    async def send_to_frontend(self, session_id: str, data: dict) -> None:
        """推消息到前端。"""
        frontend = getattr(self._bus, "frontend_service", None)
        if frontend:
            await frontend.send(session_id, data)

    async def register_component(self, session_id: str, schema: dict) -> str:
        """注册交互组件。返回 component_id。"""
        cm = getattr(self._bus, "component_manager", None)
        if not cm:
            return ""
        return await cm.register(
            session_id=session_id, tool_id=self.get_name(), schema=schema)

    async def wait_for_component(
        self, component_id: str, *, timeout: float | None = None,
    ) -> Any:
        """等待组件回调。"""
        cm = getattr(self._bus, "component_manager", None)
        if not cm:
            return None
        return await cm.wait_for_component(component_id, timeout=timeout)

    async def update_component(self, component_id: str, data: dict) -> None:
        """更新已渲染的组件。"""
        cm = getattr(self._bus, "component_manager", None)
        if cm:
            await cm.update_component(component_id, data)

    async def destroy_component(self, component_id: str) -> None:
        """销毁组件。"""
        cm = getattr(self._bus, "component_manager", None)
        if cm:
            await cm.destroy_component(component_id)
