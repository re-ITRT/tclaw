"""Gateway —— 前端接入层 + 组件注册中心。

角色：
  1. 网络服务 — FastAPI + WebSocket
  2. 连接管理 — SessionManager（session.py）
  3. 消息路由 — 用户文本→EventBus / 工具事件→Tool 直调
  4. EventBus 订阅 — AGENT_OUTPUT/TOOL_RESULT → 推前端
  5. 组件注册中心 — ComponentManager

架构：
   前端                      Gateway                    EventBus/Tools
    │                         │                            │
    ├─ WS:text ──────────────→│  publish ─────────────────→│ EventBus
    │                         │                            │
    ├─ WS:tool_event ────────→│  get_tool().handle_        │
    │                         │    gateway_event() 直调 ──→│ Tool
    │                         │                            │
    ├─ WS:component_callback →│  cm.resolve_callback()     │
    │                         │                            │
    │                         │← subscribe ───────────────│ EventBus
    │← WS:push ──────────────│                            │
    │                         │                            │
    │← WS:component_register ─│← cm.register()            │ Tool 直调
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .component_manager import (
    ComponentManager,
    GatewayComponentManager,
)
from .session import SessionManager

if TYPE_CHECKING:
    from ..common.event_bus import EventBus

logger = logging.getLogger("tclaw.gateway")


# ── Gateway 主类 ────────────────────────────────────────────


class Gateway:
    """前端接入层。管理连接、路由消息、注册组件。"""

    def __init__(
        self,
        bus: EventBus,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.bus = bus
        self.host = host
        self.port = port

        # 组件注册中心 — 迁移到 FrontendService
        from .frontend_service import FrontendService
        self.frontend = FrontendService(self)

        # Session 管理
        self.sessions = SessionManager(
            bus=bus,
            component_manager=self.frontend.component_manager,
            session_timeout=1800,
        )

        # 注册到 EventBus
        bus.frontend_service = self.frontend
        bus._gateway = self  # 向后兼容
        bus.component_manager = self.frontend.component_manager

        logger.info("Gateway initialized (host=%s, port=%d)", host, port)

    # ── WebSocket 消息路由 ───────────────────────────────

    async def handle_ws_message(self, ws, data: dict) -> None:
        """处理 WebSocket 消息。由 app.py 的路由调用。"""
        session_id = SessionManager.session_id_from_ws(ws)

        msg_type = data.get("type", "")

        if msg_type == "text":
            await self._handle_text(data, session_id)

        elif msg_type == "tool_event":
            await self._handle_tool_event(data, session_id)

        elif msg_type == "component_callback":
            self._handle_component_callback(data)

        elif msg_type == "cancel":
            self._handle_cancel(session_id)

        elif msg_type == "reset":
            self._handle_reset(session_id)

        elif msg_type == "compact":
            await self._handle_compact(data, session_id)

        else:
            logger.warning("unknown message type: %s", msg_type)

    async def _handle_text(self, data: dict, session_id: str) -> None:
        """用户文本 → user_input tool.handle_gateway_event()。同时记录到前端事件库。"""
        text = data.get("content", "")
        if text:
            self.frontend._no_ws = True
            await self.frontend.send(session_id, {
                "type": "chat_history", "role": "user", "content": text,
            })
        tool = self.bus.get_tool("user_input")
        if tool:
            await tool.handle_gateway_event(
                data={"content": text, "files": data.get("files", [])},
                session_id=session_id,
            )

    async def _handle_tool_event(self, data: dict, session_id: str) -> None:
        """前端工具交互 → Tool.handle_gateway_event() 直调。"""
        tool_id = data.get("tool", "")
        tool = self.bus.get_tool(tool_id)
        if tool:
            try:
                await tool.handle_gateway_event(
                    data=data.get("data", {}),
                    session_id=session_id,
                )
            except Exception:
                logger.exception("tool handle_gateway_event failed: %s", tool_id)
        else:
            logger.warning("tool not found: %s", tool_id)
            await self.sessions.send(session_id, {
                "type": "error",
                "code": "TOOL_NOT_FOUND",
                "message": f"tool '{tool_id}' not found",
            })

    def _handle_component_callback(self, data: dict) -> None:
        """组件回调 → ComponentManager.resolve_callback()。"""
        self.frontend.resolve_callback(
            component_id=data.get("component_id", ""),
            result=data.get("result", {}),
        )

    def _handle_cancel(self, session_id: str) -> None:
        """取消当前 session 的推理。"""
        logger.info("cancel requested for session: %s", session_id)
        # TODO: Phase 2

    def _handle_reset(self, session_id: str) -> None:
        """重置 session：清历史 + 清事件 + 重建 ContextManager。"""
        ctx = self.bus._get_context_mgr(session_id)
        if ctx:
            import asyncio
            asyncio.create_task(ctx.clear())
        self.frontend.delete_session_events(session_id)
        self.frontend.cleanup_session(session_id)
        logger.info("session reset: %s", session_id)

    async def _handle_compact(self, data: dict, session_id: str) -> None:
        """触发上下文压缩。"""
        prompt = data.get("prompt", "") if isinstance(data, dict) else ""
        await self.bus.publish({
            "topic": "extension.compactor.compact",
            "payload": {"session_id": session_id, "prompt": prompt},
            "session_id": session_id,
        })
        logger.info("compact requested: %s", session_id)

    # ── 前端辅助 ─────────────────────────────────────────

    async def send(self, session_id: str, data: dict) -> None:
        """推消息到前端。Tool / ComponentManager 调此方法。"""
        await self.sessions.send(session_id, data)

    # ── 生命周期 ──────────────────────────────────────────

    def cleanup_session(self, session_id: str) -> None:
        self.sessions.cleanup(session_id)

    async def restore_session(self, session_id: str) -> None:
        """重建前端会话状态（断线重连后用）。从事件数据库回放。"""
        events = self.frontend.get_session_events(session_id)
        if not events:
            return

        self.frontend._replaying = True
        try:
            # 跳过旧的 component_register（重启后 component_manager 里没有这些组件）
            active_component_ids = set()
            for ev in events:
                if ev.get("type") == "component_register":
                    cid = ev.get("component_id", "")
                    if cid not in self.frontend.component_manager._components:
                        continue  # 组件已不在追踪中，跳过
                await self.frontend.send(session_id, ev)
        finally:
            self.frontend._replaying = False
