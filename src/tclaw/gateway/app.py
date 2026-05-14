"""FastAPI 应用入口。提供 WebSocket + REST 端点 + 组件静态路由。"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from starlette.responses import FileResponse, HTMLResponse

from .gateway import Gateway
from .logs import get_logs, clear_logs, install_log_capture

logger = logging.getLogger("tclaw.gateway.app")

# tclaw 项目根目录（frontend/ 所在位置）
_TCLAW_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FRONTEND_DIR = _TCLAW_ROOT / "frontend"


def create_app(gateway: Gateway) -> FastAPI:
    """创建 FastAPI 应用，绑定 Gateway 路由。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        install_log_capture()
        logger.info("gateway app started")
        yield
        logger.info("gateway app stopped")

    app = FastAPI(lifespan=lifespan)

    # ── WebSocket 端点 ──────────────────────────────────

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(ws: WebSocket, session_id: str):
        await ws.accept()
        ws.state.session_id = session_id

        try:
            conn = gateway.sessions.get_or_create(ws, session_id)
            # 重建前端会话状态（历史消息 + 活跃组件）
            await gateway.restore_session(session_id)
        except Exception:
            logger.exception("failed to create connection: session=%s", session_id)
            await ws.close(code=1011)
            return

        try:
            while True:
                data = await ws.receive_json()
                await gateway.handle_ws_message(ws, data)
        except WebSocketDisconnect:
            logger.info("websocket disconnected: session=%s", session_id)
        except Exception:
            logger.exception("websocket error: session=%s", session_id)
        finally:
            gateway.sessions.remove(session_id)

    # ── 前端页面 ──────────────────────────────────────────

    @app.get("/")
    async def index():
        frontend_path = _FRONTEND_DIR / "index.html"
        if frontend_path.is_file():
            return HTMLResponse(frontend_path.read_text(encoding="utf-8"))
        return Response(status_code=404, content="frontend/index.html not found")

    # ── Tool 组件静态路由 ──────────────────────────────
    #
    # 提供 Tool 目录下 component/ 文件夹中的文件。
    # 前端通过 iframe src="/components/{tool_id}/index.html" 加载。

    @app.get("/components/{tool_id}/{filename:path}")
    async def serve_component(tool_id: str, filename: str):
        tool = gateway.bus.get_tool(tool_id)
        if not tool:
            return Response(status_code=404, content="tool not found")

        comp_dir = os.path.join(tool._tool_dir, "component")
        comp_path = os.path.normpath(os.path.join(comp_dir, filename))

        # 防路径穿越
        if not comp_path.startswith(os.path.normpath(comp_dir)):
            return Response(status_code=403, content="forbidden")

        if not os.path.isfile(comp_path):
            return Response(status_code=404, content="file not found")

        return FileResponse(comp_path)

    # ── REST 端点 ───────────────────────────────────────

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "connections": gateway.sessions.count,
            "tools": list(gateway.bus.registered_tools.keys()),
        }

    @app.get("/api/logs")
    async def api_logs(level: str | None = None):
        logs = get_logs()
        if level:
            logs = [r for r in logs if r["level"] == level.upper()]
        return {"logs": logs[-200:]}  # 最多返回 200 条

    @app.post("/api/logs/clear")
    async def api_logs_clear():
        clear_logs()
        return {"status": "cleared"}

    @app.get("/api/settings")
    async def get_settings():
        return {
            "llm_model": gateway.bus.llm.model if gateway.bus.llm else "not set",
            "connections": gateway.sessions.count,
        }

    @app.get("/api/sessions")
    async def api_sessions():
        return {"sessions": gateway.frontend.list_sessions()}

    @app.get("/api/sessions/{session_id}/history")
    async def api_session_history(session_id: str):
        return {"history": gateway.frontend.get_session_history(session_id)}

    @app.delete("/api/sessions/{session_id}")
    async def api_session_delete(session_id: str):
        ok = gateway.frontend.delete_session(session_id)
        return {"status": "deleted" if ok else "not_found"}

    @app.post("/api/session/{session_id}/clear")
    async def clear_session(session_id: str):
        ctx = gateway.bus._get_context_mgr(session_id)
        if ctx:
            await ctx.clear()
        gateway.cleanup_session(session_id)
        gateway.frontend.delete_session_events(session_id)
        return {"status": "cleared", "session_id": session_id}

    @app.get("/api/tools")
    async def api_tools():
        """列出所有工具。跳过 TOOL.md 的 YAML front matter 提取描述。"""
        tools = []
        for tid, t in gateway.bus.registered_tools.items():
            # 提取描述：跳过 YAML front matter
            desc = ""
            md = t.tool_md.strip()
            if md:
                lines = md.split(chr(10))
                start = 0
                if lines and lines[0].strip() == "---":
                    for i in range(1, len(lines)):
                        if lines[i].strip() == "---":
                            start = i + 1
                            break
                for i in range(start, len(lines)):
                    line = lines[i].strip()
                    if line and not line.startswith("#"):
                        desc = line[:120]
                        break
            tools.append({"id": tid, "description": desc})
        return {"tools": tools}

    @app.get("/api/extensions")
    async def api_extensions():
        exts = []
        for eid, e in gateway.bus.registered_extensions.items():
            exts.append({"id": eid})
        return {"extensions": exts}

    @app.get("/api/skills")
    async def api_skills():
        """列出所有技能及开关状态。"""
        import os
        from tclaw.common.settings import SKILLS_DIR
        from tclaw.common.skills import is_skill_enabled, discover_skills
        skills = []
        for name in discover_skills():
            md_path = os.path.join(SKILLS_DIR, name, "SKILL.md")
            desc = ""
            if os.path.isfile(md_path):
                with open(md_path, "r", encoding="utf-8") as f:
                    desc = f.read().strip()
            skills.append({
                "id": name,
                "description": desc,
                "enabled": is_skill_enabled(name),
            })
        return {"skills": skills}

    @app.post("/api/skills/{name}/toggle")
    async def api_toggle_skill(name: str):
        """切换技能的启用/禁用状态。"""
        from tclaw.common.skills import is_skill_enabled, enable_skill, disable_skill, discover_skills
        if name not in discover_skills():
            return {"status": "error", "message": f"skill not found: {name}"}
        if is_skill_enabled(name):
            disable_skill(name)
            enabled = False
        else:
            enable_skill(name)
            enabled = True
        return {"status": "ok", "skill": name, "enabled": enabled}

    @app.get("/s/{filename:path}")
    async def serve_static(filename: str):
        """Serve static files from frontend/."""
        import os
        file_path = os.path.normpath(str(_FRONTEND_DIR / filename))
        if os.path.isfile(file_path) and file_path.startswith(str(_FRONTEND_DIR)):
            return FileResponse(file_path)
        return Response(status_code=404, content="not found")

    # ── 子工作区 API ──────────────────────────────────────

    @app.get("/api/workspaces")
    async def api_workspaces():
        from tclaw.common.sub_workspace import list_workspaces
        return {"workspaces": list_workspaces()}

    @app.post("/api/workspaces/create")
    async def api_create_workspace(data: dict):
        from tclaw.common.sub_workspace import create_workspace
        session_id = data.get("session_id", "")
        if not session_id or not session_id.startswith("sub:"):
            return {"status": "error", "message": "session_id must start with 'sub:'"}
        path = create_workspace(session_id)
        return {"status": "ok", "session_id": session_id, "path": path}

    @app.post("/api/workspaces/{name}/clone")
    async def api_clone_workspace(name: str, data: dict):
        from tclaw.common.sub_workspace import clone_workspace
        new_id = data.get("new_id", "")
        if not new_id:
            return {"status": "error", "message": "new_id required"}
        try:
            path = clone_workspace(name, new_id)
            return {"status": "ok", "session_id": new_id, "path": path}
        except (FileExistsError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/workspaces/{name}/fork")
    async def api_fork_workspace(name: str, data: dict):
        from tclaw.common.sub_workspace import fork_workspace
        new_id = data.get("new_id", name)
        try:
            path = fork_workspace(name, new_id)
            return {"status": "ok", "session_id": new_id, "path": path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @app.post("/api/workspaces/from-template")
    async def api_from_template(data: dict):
        from tclaw.common.sub_workspace import use_template
        template_name = data.get("template", "")
        new_id = data.get("new_id", "")
        if not template_name or not new_id:
            return {"status": "error", "message": "template and new_id required"}
        path = use_template(template_name, new_id)
        return {"status": "ok", "session_id": new_id, "path": path, "template": template_name}

    @app.post("/api/workspaces/{name}/template")
    async def api_create_template(name: str, data: dict):
        """从 session 创建模板。"""
        from tclaw.common.sub_workspace import create_template
        template_name = data.get("template_name", "") or name
        try:
            path = create_template(name, template_name)
            return {"status": "ok", "template": template_name, "path": path}
        except (FileExistsError, FileNotFoundError) as e:
            return {"status": "error", "message": str(e)}

    @app.delete("/api/workspaces/{name}")
    async def api_delete_workspace(name: str):
        from tclaw.common.sub_workspace import delete_workspace
        ok = delete_workspace(name)
        return {"status": "deleted" if ok else "error", "name": name}

    return app


# ── 启动 ─────────────────────────────────────────────────────


async def start_gateway(gateway: Gateway) -> asyncio.Task:
    import uvicorn

    app = create_app(gateway)
    config = uvicorn.Config(
        app,
        host=gateway.host,
        port=gateway.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # 用 socket 手动绑定，再启动 server
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((gateway.host, gateway.port))
    sock.listen()
    sock.setblocking(False)

    task = asyncio.create_task(server.serve(sockets=[sock]))
    logger.info("gateway listening on ws://%s:%d", gateway.host, gateway.port)
    return task, server
