"""SessionManager —— Session 生命周期管理。

管理 WebSocket 连接映射、自动创建 ContextManager、断线重连、过期清理。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger("tclaw.gateway.session")


# ── Connection 包装 ─────────────────────────────────────────


class Connection:
    """WS 连接包装。支持 send_json 和 session_id。"""

    def __init__(self, ws: WebSocket, session_id: str) -> None:
        self._ws = ws
        self._session_id = session_id
        self._connected = True
        self._created_at = time.time()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def age(self) -> float:
        return time.time() - self._created_at

    async def send_json(self, data: dict) -> None:
        if not self._connected:
            return
        try:
            await self._ws.send_json(data)
        except Exception:
            self._connected = False

    def mark_disconnected(self) -> None:
        self._connected = False

    async def close(self) -> None:
        self._connected = False
        try:
            await self._ws.close()
        except Exception:
            pass


# ── SessionManager ────────────────────────────────────────────


class SessionManager:
    """Session 生命周期管理。"""

    def __init__(
        self,
        bus,                        # EventBus
        component_manager,          # ComponentManager
        session_timeout: float = 1800,  # 30 分钟
    ) -> None:
        self._bus = bus
        self._cm = component_manager
        self._connections: dict[str, Connection] = {}
        self._timeout = session_timeout
        logger.debug("SessionManager initialized (timeout=%.0fs)", session_timeout)

    # ── 基本操作 ──────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._connections)

    def has(self, session_id: str) -> bool:
        conn = self._connections.get(session_id)
        return conn is not None and conn.connected

    def get(self, session_id: str) -> Connection | None:
        return self._connections.get(session_id)

    # ── 连接生命周期 ──────────────────────────────────────

    def get_or_create(self, ws: WebSocket, session_id: str) -> Connection:
        """获取或创建连接。已存在则替换 WS（支持重连）。"""
        conn = self._connections.get(session_id)
        if conn and conn.connected:
            conn.mark_disconnected()

        conn = Connection(ws, session_id)
        self._connections[session_id] = conn

        # 确保 session 有 ContextManager
        self._bus._get_context_mgr(session_id)

        logger.info("connection established: session=%s", session_id)
        return conn

    def remove(self, session_id: str) -> None:
        """断开连接，但保留 session（重连等待期内可恢复）。"""
        conn = self._connections.pop(session_id, None)
        if conn:
            conn.mark_disconnected()
            logger.info("connection removed: session=%s", session_id)

    def cleanup(self, session_id: str) -> None:
        """彻底清理 session：销毁组件 + 断开连接。"""
        self._cm.cleanup_session(session_id)
        self.remove(session_id)
        logger.info("session cleaned up: %s", session_id)

    # ── 消息推送 ──────────────────────────────────────────

    async def send(self, session_id: str, data: dict) -> None:
        """向 session 推送消息。连接不存在则静默忽略。"""
        conn = self._connections.get(session_id)
        if conn:
            await conn.send_json(data)

    # ── Session ID 提取 ───────────────────────────────────

    @staticmethod
    def session_id_from_ws(ws: WebSocket) -> str:
        """从 WebSocket 对象中提取 session_id。

        由 app 在握手时绑定到 ws.state.session_id。
        """
        return getattr(ws.state, "session_id", "")
