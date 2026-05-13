"""tclaw 全局配置。

从 config.json 读取，环境变量覆盖。
不存在 config.json 时自动创建模板（不含 api_key）。

优先级：环境变量 > config.json > 默认值

配置路径用点号分隔，环境变量用大写加下划线：
  llm.model      →  LLM_MODEL
  llm.max_tokens →  LLM_MAX_TOKENS
  gateway.host   →  GATEWAY_HOST
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _find_config() -> dict:
    """查找并加载 config.json。不存在则自动创建模板。"""
    here = Path(__file__).resolve().parent.parent.parent.parent  # tclaw/ 项目根
    candidates = [
        here / "config.json",
        Path.cwd() / "config.json",
        Path.home() / ".tclaw" / "config.json",
        Path(os.environ.get("TCLAW_CONFIG", "")),
    ]
    for path in candidates:
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    # 不存在 → 在项目根创建模板（不含 api_key）
    template = _default_config()
    try:
        template_path = here / "config.json"
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
    return template


def _default_config() -> dict:
    return {
        "llm": {
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com/v1",
            "max_tokens": 8192,
        },
        "gateway": {
            "host": "0.0.0.0",
            "port": 8080,
        },
        "workspace": "~/tclaw/workspace",
        "log_level": "INFO",
    }


_config = _find_config()


def _get(dotted: str, default: str = "") -> str:
    """读配置：环境变量优先 > config.json > 默认值。"""
    # 环境变量优先
    env_key = dotted.upper().replace(".", "_")
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val

    # config.json 嵌套遍历
    cursor: dict | str | int = _config
    for part in dotted.split("."):
        if isinstance(cursor, dict):
            cursor = cursor.get(part, {})
        else:
            return default
    if isinstance(cursor, str):
        return cursor
    if isinstance(cursor, (int, float)):
        return str(cursor)
    return default


# ── 路径 ────────────────────────────────────────────────────

WORKSPACE_DIR: str = _get("workspace", os.path.expanduser("~/tclaw/workspace"))
MEMORY_DIR: str = os.path.join(WORKSPACE_DIR, "memory")
MEMORY_FILE: str = os.path.join(MEMORY_DIR, "MEMORY.md")
MEMORY_DAILY_DIR: str = os.path.join(MEMORY_DIR, "daily")
MEMORY_INDEX_DB: str = os.path.join(MEMORY_DIR, "index.db")

def resolve_path(path: str) -> str:
    """Resolve file path. Relative paths use WORKSPACE_DIR as root."""
    expanded = os.path.expanduser(path)
    if expanded.startswith("/"):
        return os.path.abspath(expanded)
    return os.path.normpath(os.path.join(WORKSPACE_DIR, expanded))


# ── Skills ──────────────────────────────────────────────────

SKILLS_DIR: str = os.path.join(WORKSPACE_DIR, "skills")
SESSION_DIR: str = os.path.join(WORKSPACE_DIR, "logs", "sessions")

# ── Agent 配置 ─────────────────────────────────────────────

AGENT_SOUL: str = os.path.join(MEMORY_DIR, "SOUL.md")
AGENT_USER: str = os.path.join(MEMORY_DIR, "USER.md")
AGENT_IDENTITY: str = os.path.join(MEMORY_DIR, "IDENTITY.md")
AGENT_TOOLS: str = os.path.join(MEMORY_DIR, "TOOLS.md")
AGENT_HEARTBEAT: str = os.path.join(MEMORY_DIR, "HEARTBEAT.md")

# ── LLM ──────────────────────────────────────────────────────

LLM_MODEL: str = _get("llm.model", "deepseek-v4-flash")
LLM_BASE_URL: str = _get("llm.base_url", "https://api.deepseek.com/v1")
LLM_API_KEY: str = _get("llm.api_key", "")
LLM_MAX_TOKENS: int = int(_get("llm.max_tokens", "8192"))

# ── Gateway ──────────────────────────────────────────────────

GATEWAY_HOST: str = _get("gateway.host", "0.0.0.0")
GATEWAY_PORT: int = int(_get("gateway.port", "8080"))

# ── 日志 ────────────────────────────────────────────────────

LOG_LEVEL: str = _get("log_level", "INFO")
