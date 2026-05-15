"""会话管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["sessions"])


def register(app, gateway):
    """将会话路由注册到 app。"""

    @app.get("/api/sessions")
    async def api_sessions():
        """列出所有有事件的 session。"""
        return {"sessions": gateway.frontend.list_sessions()}

    @app.get("/api/sessions/{session_id}/history")
    async def api_session_history(session_id: str):
        """读取指定 session 的 LLM 对话历史。"""
        return {"history": gateway.frontend.get_session_history(session_id)}

    @app.delete("/api/sessions/{session_id}")
    async def api_session_delete(session_id: str):
        """删除 session 记录。"""
        ok = gateway.frontend.delete_session(session_id)
        return {"status": "deleted" if ok else "not_found"}

    @app.post("/api/session/{session_id}/clear")
    async def clear_session(session_id: str):
        """清空 session 的对话历史 + 前端事件。"""
        ctx = gateway.bus._get_context_mgr(session_id)
        if ctx:
            await ctx.clear()
        gateway.cleanup_session(session_id)
        gateway.frontend.delete_session_events(session_id)
        return {"status": "cleared", "session_id": session_id}
