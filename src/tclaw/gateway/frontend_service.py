"""FrontendService —— 统一前端通信层。

Tools 通过 bus.frontend_service 访问前端，不直接碰 Gateway。
同时管理聊天记录的持久化和加载。
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

from ..common.settings import SESSION_DIR
from .component_manager import GatewayComponentManager

if TYPE_CHECKING:
    from .gateway import Gateway

logger = logging.getLogger("tclaw.gateway.frontend")


class FrontendService:
    """前端通信服务。Tools 的唯一前端接口 + 聊天记录管理。"""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self.component_manager = GatewayComponentManager(gateway)
        os.makedirs(SESSION_DIR, exist_ok=True)
        logger.debug("FrontendService initialized (session_dir=%s)", SESSION_DIR)

    async def send(self, session_id: str, data: dict) -> None:
        """推消息到前端。"""
        await self._gateway.sessions.send(session_id, data)

    def resolve_callback(self, component_id: str, result: Any) -> None:
        """组件回调。"""
        self.component_manager.resolve_callback(component_id, result)

    def cleanup_session(self, session_id: str) -> None:
        """清理 session 组件。"""
        self.component_manager.cleanup_session(session_id)

    # ── 聊天记录管理 ───────────────────────────────────

    def list_sessions(self) -> list[dict]:
        """列出所有有聊天记录的 session。"""
        if not os.path.isdir(SESSION_DIR):
            return []
        sessions = []
        for name in sorted(os.listdir(SESSION_DIR), reverse=True):
            if not name.endswith(".json"):
                continue
            sid = name[:-5]  # 去掉 .json
            path = os.path.join(SESSION_DIR, name)
            try:
                mtime = os.path.getmtime(path)
                size = os.path.getsize(path)
            except OSError:
                continue
            # 取第一条消息作为预览
            preview = ""
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                history = data.get("history", [])
                for msg in history:
                    content = msg.get("content", "")
                    if content.strip():
                        preview = content[:80]
                        break
            except Exception:
                pass
            sessions.append({
                "id": sid,
                "mtime": mtime,
                "messages": len(data.get("history", [])) if 'data' in dir() else 0,
                "preview": preview,
            })
        return sessions

    def get_session_history(self, session_id: str) -> list[dict]:
        """读取指定 session 的聊天记录。"""
        path = os.path.join(SESSION_DIR, f"{session_id}.json")
        if not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("history", [])
        except Exception:
            return []

    def delete_session(self, session_id: str) -> bool:
        """删除指定 session 的聊天记录。"""
        path = os.path.join(SESSION_DIR, f"{session_id}.json")
        if os.path.isfile(path):
            try:
                os.remove(path)
                return True
            except OSError:
                pass
        return False
