"""会话管理 API 路由。"""
from __future__ import annotations

import os

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


    @app.get("/api/conversations/search")
    async def search_conversations(q: str = "", limit: int = 20):
        """搜索对话历史。"""
        from tclaw.gateway.frontend_service import FrontendService
        import json, sqlite3
        db_path = os.path.join(gateway.frontend._db_path) if hasattr(gateway.frontend, '_db_path') else ""
        if not db_path or not os.path.isfile(db_path):
            return {"results": []}
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT session_id, type, payload FROM frontend_events "
                "WHERE type IN ('assistant','chat_history') AND payload LIKE ? "
                "ORDER BY seq DESC LIMIT ?",
                (f"%{q}%", limit) if q else ("%", limit),
            ).fetchall()
            conn.close()
            results = []
            for sid, typ, payload in rows:
                try:
                    data = json.loads(payload)
                    content = data.get("content", "") if isinstance(data, dict) else ""
                    results.append({"session_id": sid, "type": typ, "content": content[:200]})
                except Exception:
                    pass
            return {"results": results, "query": q}
        except Exception as e:
            return {"results": [], "error": str(e)}
