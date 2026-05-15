"""日志 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["logs"])


def register(app, gateway):
    """注册日志路由。"""
    from ..logs import get_logs, clear_logs

    @app.get("/api/logs")
    async def api_logs(limit: int = 100, level: str = ""):
        """获取日志（可选过滤级别和行数）。"""
        logs = get_logs(limit=limit)
        if level:
            logs = [l for l in logs if l.get("level", "").lower() == level.lower()]
        return {"logs": logs}

    @app.post("/api/logs/clear")
    async def api_logs_clear():
        """清空内存中的日志。"""
        clear_logs()
        return {"status": "cleared"}
