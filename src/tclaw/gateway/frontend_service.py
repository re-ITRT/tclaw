"""FrontendService —— 统一前端通信层 + 事件持久化。

每一条发往前端的消息都被记录到 SQLite 数据库中。
断线重连时从数据库回放，恢复聊天和组件的完整状态。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import TYPE_CHECKING, Any

from ..common.settings import SESSION_DIR
from .component_manager import GatewayComponentManager

if TYPE_CHECKING:
    from .gateway import Gateway

logger = logging.getLogger("tclaw.gateway.frontend")


class FrontendService:
    """前端通信服务。所有发往前端的消息都经过此服务，并持久化到 SQLite。"""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self.component_manager = GatewayComponentManager(self)
        self._replaying = False  # 回放时不重复记录
        self._no_ws = False  # 仅记录不推送（如用户消息）
        os.makedirs(SESSION_DIR, exist_ok=True)
        self._db_path = os.path.join(SESSION_DIR, "events.db")
        self._local = threading.local()
        self._init_db()
        logger.debug("FrontendService initialized (events_db=%s)", self._db_path)

    # ── 数据库 ───────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """每个线程独立连接。"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS frontend_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                seq         INTEGER NOT NULL,
                timestamp   REAL NOT NULL,
                type        TEXT NOT NULL,
                payload     TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_frontend_events_session
            ON frontend_events(session_id, seq)
        """)
        conn.commit()

    async def send(self, session_id: str, data: dict) -> None:
        """推消息到前端，同时持久化（回放时跳过记录）。"""
        if not session_id:
            return

        if not self._replaying:
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO frontend_events (session_id, seq, timestamp, type, payload) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, int(time.time() * 1000), time.time(),
                     data.get("type", ""), json.dumps(data, ensure_ascii=False)),
                )
                conn.commit()
            except Exception as e:
                logger.warning("failed to persist frontend event: %s", e)

        if not self._no_ws:
            await self._gateway.sessions.send(session_id, data)
        self._no_ws = False

    # ── 事件回放 ─────────────────────────────────────────

    def get_session_events(self, session_id: str) -> list[dict]:
        """读取指定 session 的所有前端事件，按 seq 排序。"""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT payload FROM frontend_events "
                "WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        except Exception as e:
            logger.warning("failed to read session events: %s", e)
            return []

    def delete_session_events(self, session_id: str) -> None:
        """删除指定 session 的所有事件。"""
        try:
            conn = self._get_conn()
            conn.execute("DELETE FROM frontend_events WHERE session_id = ?", (session_id,))
            conn.commit()
        except Exception as e:
            logger.warning("failed to delete session events: %s", e)

    # ── 组件回调 ─────────────────────────────────────────

    def resolve_callback(self, component_id: str, result: Any) -> None:
        """组件回调。"""
        self.component_manager.resolve_callback(component_id, result)

    def cleanup_session(self, session_id: str) -> None:
        """清理 session 组件。"""
        self.component_manager.cleanup_session(session_id)

    # ── 会话管理 ─────────────────────────────────────────

    def list_sessions(self) -> list[dict]:
        """列出所有有事件的 session（从数据库读）。"""
        try:
            conn = self._get_conn()
            rows = conn.execute("""
                SELECT session_id, MIN(timestamp) as first, MAX(timestamp) as last, COUNT(*) as cnt
                FROM frontend_events GROUP BY session_id ORDER BY last DESC
            """).fetchall()
            sessions = []
            for sid, first_ts, last_ts, count in rows:
                # 第一条 assistant 消息作为预览
                preview = ""
                first_msgs = conn.execute(
                    "SELECT payload FROM frontend_events WHERE session_id = ? AND type = 'assistant' "
                    "ORDER BY seq ASC LIMIT 1", (sid,)
                ).fetchone()
                if first_msgs:
                    try:
                        payload = json.loads(first_msgs[0])
                        preview = (payload.get("content") or "")[:80]
                    except Exception:
                        pass
                sessions.append({
                    "id": sid,
                    "mtime": int(last_ts or 0),
                    "messages": count,
                    "preview": preview,
                })
            return sessions
        except Exception as e:
            logger.warning("failed to list sessions: %s", e)
            return []

    def delete_session(self, session_id: str) -> bool:
        """删除 session 的所有前端事件 + 会话状态。"""
        self.delete_session_events(session_id)
        # 也删除会话状态文件
        session_file = os.path.join(SESSION_DIR, f"{session_id}.json")
        if os.path.isfile(session_file):
            try:
                os.remove(session_file)
                return True
            except OSError:
                pass
        return True

    def get_session_history(self, session_id: str) -> list[dict]:
        """读取 session 的 LLM 对话历史（兼容旧接口）。"""
        path = os.path.join(SESSION_DIR, f"{session_id}.json")
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("history", [])
        except Exception:
            return []
