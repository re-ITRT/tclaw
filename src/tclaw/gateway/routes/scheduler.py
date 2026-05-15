"""定时任务 API 路由。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

router = APIRouter(tags=["scheduler"])


def register(app, gateway):
    """注册定时任务路由。"""

    @app.get("/api/scheduler")
    async def api_scheduler_list():
        """获取所有定时任务。"""
        tool = gateway.bus.get_tool("scheduler")
        return {"tasks": tool.get_tasks() if tool else []}

    @app.post("/api/scheduler")
    async def api_scheduler_add(data: dict):
        """添加定时任务。"""
        tool = gateway.bus.get_tool("scheduler")
        if not tool:
            return {"status": "error", "message": "scheduler not loaded"}
        tid = data.get("id", "") or data.get("name", "") or f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tool.add_task(tid, {
            "id": tid,
            "name": data.get("name", tid),
            "target_session": data.get("target_session", data.get("session_id", "main")),
            "message": data.get("message", ""),
            "schedule": data.get("schedule", {}),
            "last_fired": 0, "disabled": False,
            "created_at": datetime.now().isoformat(),
        })
        return {"status": "ok", "id": tid}

    @app.delete("/api/scheduler/{task_id}")
    async def api_scheduler_remove(task_id: str):
        """删除定时任务。"""
        tool = gateway.bus.get_tool("scheduler")
        if tool:
            tool.remove_task(task_id)
        return {"status": "deleted", "id": task_id}
