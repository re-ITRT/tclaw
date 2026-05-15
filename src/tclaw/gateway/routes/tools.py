"""工具与扩展 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["tools"])


def register(app, gateway):
    """注册工具/扩展/健康相关路由。"""

    @app.get("/api/health")
    async def api_health():
        """健康检查。"""
        tools = list(gateway.bus.registered_tools.keys())
        return {"status": "ok", "connections": gateway.sessions.count, "tools": tools}

    @app.get("/api/tools")
    async def api_tools():
        """列出所有 tool 及 YAML 头部描述。"""
        tools = []
        for tid, t in gateway.bus.registered_tools.items():
            desc = _extract_tool_description(t)
            tools.append({"id": tid, "description": desc})
        return {"tools": tools}

    @app.get("/api/extensions")
    async def api_extensions():
        """列出所有 extension。"""
        exts = [{"id": eid} for eid in gateway.bus.registered_extensions]
        return {"extensions": exts}

    @app.get("/api/settings")
    async def api_settings():
        """当前配置（不含密钥）。"""
        return {
            "workspace": str(gateway.bus._get_context_mgr("main")._init_prompt[:100])
            if gateway.bus._get_context_mgr("main") else "",
        }

    @app.get("/api/usage")
    async def api_usage(session_id: str = ""):
        """Token 用量统计。"""
        usage = getattr(gateway.bus, "_usage", {})
        if session_id:
            return {"usage": usage.get(session_id, {})}
        total_prompt = sum(u.get("prompt", 0) for u in usage.values())
        total_completion = sum(u.get("completion", 0) for u in usage.values())
        total_cached = sum(u.get("cached", 0) for u in usage.values())
        total_calls = sum(u.get("calls", 0) for u in usage.values())
        return {
            "usage": usage,
            "total": {"prompt": total_prompt, "completion": total_completion, "cached": total_cached, "calls": total_calls},
        }
    async def api_settings():
        """当前配置（不含密钥）。"""
        return {
            "workspace": str(gateway.bus._get_context_mgr("main")._init_prompt[:100])
            if gateway.bus._get_context_mgr("main") else "",
        }


def _extract_tool_description(tool) -> str:
    """从 TOOL.md 中提取第一行描述（跳过 YAML front matter）。"""
    md = tool.tool_md.strip()
    if not md:
        return ""
    lines = md.split("\n")
    # 跳过 YAML front matter (---...---)
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    # 找到第一个非空、非标题行
    for i in range(start, len(lines)):
        line = lines[i].strip()
        if line and not line.startswith("#"):
            return line[:120]
    return ""

