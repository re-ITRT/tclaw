"""UsageExtension —— Token 用量统计。

订阅 tool.invoke.output:after，当 mode=end 时统计该轮用量。
同时维护 session 级别的累积统计。
数据暴露给 /api/usage 和前端使用情况标签。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

from ...common.extension import Extension

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.extensions.usage")

_USAGE_FILE: str = ""


def _get_file() -> str:
    global _USAGE_FILE
    if not _USAGE_FILE:
        from ...common.settings import WORKSPACE_DIR
        _USAGE_FILE = os.path.join(WORKSPACE_DIR, ".usage_stats.json")
    return _USAGE_FILE


def _load_stats() -> dict:
    path = _get_file()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sessions": {}}


def _save_stats(stats: dict) -> None:
    with open(_get_file(), "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


class UsageExtension(Extension):
    """Token 用量统计扩展。"""

    ext_id = "usage"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._stats = _load_stats()
        bus.subscribe("tool.invoke.output:after", self._on_output)
        bus.subscribe("extension.usage.query", self._on_query)
        logger.info("usage extension active")

    async def _on_output(self, event: dict) -> None:
        """LLM 输出后统计用量。"""
        payload = event.get("payload", {})
        mode = payload.get("mode", "")
        sid = payload.get("session_id", "") or event.get("session_id", "")
        if not sid:
            return

        # 从 EventBus 获取当前 session 的 token 用量
        usage = getattr(self._bus, "_usage", {}).get(sid, {})
        prompt = usage.get("prompt", 0)
        completion = usage.get("completion", 0)
        cached = usage.get("cached", 0)
        calls = usage.get("calls", 0)

        # 更新持久化统计
        session_stats = self._stats["sessions"].setdefault(sid, {
            "total_prompt": 0, "total_completion": 0,
            "total_cached": 0, "total_calls": 0,
            "history": [],
        })

        # 只在 end 模式时记录一轮的统计
        if mode == "end":
            # 跟上一次记录之间的差值
            last = session_stats.get("last_snapshot", {})
            round_prompt = prompt - last.get("prompt", 0)
            round_completion = completion - last.get("completion", 0)
            round_cached = cached - last.get("cached", 0)
            round_calls = calls - last.get("calls", 0)

            if round_calls > 0:
                hit_rate = round(round_cached / (round_prompt or 1) * 100, 1)
                entry = {
                    "time": datetime.now().isoformat(),
                    "prompt": round_prompt,
                    "completion": round_completion,
                    "cached": round_cached,
                    "calls": round_calls,
                    "hit_rate": hit_rate,
                }
                session_stats["history"].append(entry)

                # 更新总量
                session_stats["total_prompt"] += round_prompt
                session_stats["total_completion"] += round_completion
                session_stats["total_cached"] += round_cached
                session_stats["total_calls"] += round_calls

                # 推送到前端
                await self.send_to_frontend(sid, {
                    "type": "system",
                    "content": (
                        f"📊 用量: 输入 {round_prompt}t | "
                        f"输出 {round_completion}t | "
                        f"缓存 {hit_rate}%"
                    ),
                })

            # 更新快照
            session_stats["last_snapshot"] = {
                "prompt": prompt, "completion": completion,
                "cached": cached, "calls": calls,
            }

        _save_stats(self._stats)

    async def _on_query(self, event: dict) -> None:
        """查询用量统计。"""
        sid = event.get("payload", {}).get("session_id", "") or event.get("session_id", "")
        if sid and sid in self._stats["sessions"]:
            await self.send_to_frontend(sid, {
                "type": "system",
                "content": json.dumps(self._stats["sessions"][sid], ensure_ascii=False),
            })

    def get_stats(self) -> dict:
        return self._stats
