"""SchedulerTool —— 定时任务管理。

既是 LLM 工具，也带后台循环检查任务到期。前端通过 API 操作。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from croniter import croniter

from ...common.tool import Tool
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.tools.scheduler")


def _get_file() -> str:
    from ...common.settings import WORKSPACE_DIR
    return os.path.join(WORKSPACE_DIR, ".scheduler.json")


def _load_tasks() -> dict[str, dict]:
    path = _get_file()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_tasks(tasks: dict) -> None:
    with open(_get_file(), "w") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)


class SchedulerTool(Tool):
    """定时任务管理器。后台每秒检查任务是否到期。"""

    tool_id = "scheduler"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "remove", "list"],
                "description": "add=添加任务 | remove=删除 | list=列举所有",
            },
            "id": {"type": "string", "description": "任务标识"},
            "name": {"type": "string", "description": "任务名称"},
            "target_session": {
                "type": "string",
                "description": "目标 session ID，不传则用当前 session",
            },
            "message": {"type": "string", "description": "触发时发送的消息"},
            "schedule": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["at", "every", "cron"]},
                    "at": {"type": "number"},
                    "every_ms": {"type": "number"},
                    "expr": {"type": "string"},
                },
            },
        },
        "required": ["action"],
    }

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._tasks: dict[str, dict] = _load_tasks()
        self._runner_task: asyncio.Task | None = None
        # 注册到 bus 以便前端 API 能访问
        bus._scheduler_tool = self
        logger.info("scheduler tool active (%d tasks loaded)", len(self._tasks))

    async def start_loop(self) -> None:
        """启动后台检查。由 EventBus.start() 调用。"""
        if self._runner_task is not None and not self._runner_task.done():
            return
        self._runner_task = asyncio.create_task(self._run_loop())
        logger.debug("scheduler loop started")

    async def _run_loop(self) -> None:
        """每秒检查是否有任务到期。"""
        while True:
            try:
                await asyncio.sleep(1)
                now = datetime.now(timezone.utc)
                to_fire: list[str] = []
                for tid, task in self._tasks.items():
                    if task.get("disabled", False):
                        continue
                    if self._should_fire(task, now):
                        to_fire.append(tid)
                for tid in to_fire:
                    await self._fire_task(tid)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("scheduler loop error")

    def _should_fire(self, task: dict, now: datetime) -> bool:
        last = task.get("last_fired", 0)
        sched = task.get("schedule", {})
        kind = sched.get("kind", "")
        if kind == "at":
            at_ts = sched.get("at", 0)
            if at_ts and last < at_ts and now.timestamp() * 1000 >= at_ts:
                return True
        elif kind == "every":
            interval = sched.get("every_ms", 0)
            if interval > 0 and (last == 0 or (now.timestamp() * 1000 - last) >= interval):
                return True
        elif kind == "cron":
            expr = sched.get("expr", "")
            if expr:
                try:
                    base = datetime(now.year, now.month, now.day, now.hour, now.minute)
                    if croniter.match(expr, base) and last < base.timestamp():
                        return True
                except Exception:
                    pass
        return False

    async def _fire_task(self, tid: str) -> None:
        task = self._tasks.get(tid)
        if not task:
            return
        target = task.get("target_session", "main")
        message = task.get("message", "")
        repeat = task.get("schedule", {}).get("kind", "") != "at"

        task["last_fired"] = datetime.now(timezone.utc).timestamp() * 1000
        if not repeat:
            task["disabled"] = True
        _save_tasks(self._tasks)

        logger.info("firing task %s -> session=%s", tid, target)
        await self._bus.publish({
            "topic": Topics.AGENT_MESSAGE_INCOMING,
            "payload": {"text": message, "from_session_id": f"__scheduler__:{tid}"},
            "session_id": target,
        })

        # 通知前端
        frontend = getattr(self._bus, "frontend_service", None)
        if frontend:
            await frontend.send(target, {
                "type": "system",
                "content": f"⏰ 定时任务 [{task.get('name', tid)}] 已触发",
            })

    # ── LLM 入口 ────────────────────────────────────────────

    async def do_execute(self, payload: dict) -> None:
        action = payload.get("action", "")
        sid = payload.get("session_id", "")

        if action == "list":
            tasks = self.get_tasks()
            await self.reply_to_llm({
                "status": "ok",
                "tasks": tasks,
                "message": f"共 {len(tasks)} 个定时任务",
            }, sid)

        elif action == "add":
            task_id = payload.get("id", "") or payload.get("name", "")
            if not task_id:
                task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if task_id in self._tasks:
                await self.reply_to_llm({"status": "error", "message": f"任务已存在: {task_id}"}, sid)
                return
            name = payload.get("name", task_id)
            target = payload.get("target_session", sid)
            msg = payload.get("message", "")
            sched = payload.get("schedule", {})
            if not sched.get("kind"):
                await self.reply_to_llm({"status": "error", "message": "schedule.kind required"}, sid)
                return
            self._tasks[task_id] = {
                "id": task_id, "name": name, "target_session": target,
                "message": msg, "schedule": sched,
                "last_fired": 0, "disabled": False,
                "created_at": datetime.now().isoformat(),
            }
            _save_tasks(self._tasks)
            await self.reply_to_llm({"status": "ok", "id": task_id, "message": f"任务已添加: {name}"}, sid)

        elif action == "remove":
            tid = payload.get("id", "")
            if tid in self._tasks:
                del self._tasks[tid]
                _save_tasks(self._tasks)
                await self.reply_to_llm({"status": "ok", "message": f"已删除: {tid}"}, sid)
            else:
                await self.reply_to_llm({"status": "error", "message": f"任务不存在: {tid}"}, sid)

    # ── 公开方法（供前端 API 调用） ──────────────────────────

    def get_tasks(self) -> list[dict]:
        return list(self._tasks.values())

    def add_task(self, tid: str, task: dict) -> None:
        self._tasks[tid] = task
        _save_tasks(self._tasks)

    def remove_task(self, tid: str) -> None:
        self._tasks.pop(tid, None)
        _save_tasks(self._tasks)
