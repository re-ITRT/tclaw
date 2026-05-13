"""ConversationLogger —— 对话内容持久化。

保存每次对话到 workspace/logs/conversations/ 下，
按 session 分文件，每条消息带时间戳。
"""

from __future__ import annotations

import os
from datetime import datetime

from .settings import WORKSPACE_DIR

_LOG_DIR = os.path.join(WORKSPACE_DIR, "logs", "conversations")


def _ensure_dir() -> None:
    os.makedirs(_LOG_DIR, exist_ok=True)


def _session_file(session_id: str) -> str:
    _ensure_dir()
    return os.path.join(_LOG_DIR, f"session_{session_id}.md")


def log_user(session_id: str, text: str) -> None:
    """记录用户输入。"""
    path = _session_file(session_id)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"# {ts} | session={session_id}\n")
        f.write(f"## user\n{text}\n\n")


def log_assistant(session_id: str, text: str) -> None:
    """记录 LLM 回复。"""
    if not text.strip():
        return
    path = _session_file(session_id)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"# {ts} | session={session_id}\n")
        f.write(f"## assistant\n{text}\n\n")
