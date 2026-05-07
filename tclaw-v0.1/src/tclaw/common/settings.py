"""tclaw 全局配置常量。

集中管理所有路径、默认值等硬编码，方便后续改为环境变量或配置文件。
"""

from __future__ import annotations

import os


def _default_workspace() -> str:
    return os.environ.get("TCLAW_WORKSPACE", os.path.expanduser("~/tclaw/workspace"))


# ── 路径 ────────────────────────────────────────────────────

WORKSPACE_DIR: str = _default_workspace()
MEMORY_DIR: str = os.path.join(WORKSPACE_DIR, "memory")
MEMORY_FILE: str = os.path.join(MEMORY_DIR, "MEMORY.md")
MEMORY_DAILY_DIR: str = os.path.join(MEMORY_DIR, "daily")
MEMORY_INDEX_DB: str = os.path.join(MEMORY_DIR, "index.db")

# ── Skills ──────────────────────────────────────────────────

SKILLS_DIR: str = os.path.join(WORKSPACE_DIR, "skills")

# ── Agent 配置（对应 workspace bootstrap 文件） ─────────

AGENT_SOUL: str = os.path.join(MEMORY_DIR, "SOUL.md")
AGENT_USER: str = os.path.join(MEMORY_DIR, "USER.md")
AGENT_IDENTITY: str = os.path.join(MEMORY_DIR, "IDENTITY.md")
AGENT_TOOLS: str = os.path.join(MEMORY_DIR, "TOOLS.md")
AGENT_HEARTBEAT: str = os.path.join(MEMORY_DIR, "HEARTBEAT.md")

# ── LLM ──────────────────────────────────────────────────────

LLM_MODEL: str = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "")
LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "8192"))

# ── 日志 ────────────────────────────────────────────────────

LOG_LEVEL: str = os.environ.get("TCLAW_LOG_LEVEL", "INFO")
