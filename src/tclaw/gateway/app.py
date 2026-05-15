"""FastAPI 应用入口。提供 WebSocket + 静态文件 + 组件路由。

路由按功能分散到 routes/ 模块，此处只注册核心端点。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from starlette.responses import FileResponse, HTMLResponse

from .gateway import Gateway
from .logs import install_log_capture
from .routes import logs as route_logs
from .routes import sessions as route_sessions
from .routes import tools as route_tools
from .routes import skills as route_skills
from .routes import workspace as route_workspace
from .routes import scheduler as route_scheduler

logger = logging.getLogger("tclaw.gateway.app")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"


def create_app(gateway: Gateway) -> FastAPI:
    """创建 FastAPI 应用，绑定所有路由。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        install_log_capture()
        logger.debug("gateway capturing logs")
        yield

    app = FastAPI(lifespan=lifespan)

    _register_views(app, gateway)
    _register_websocket(app, gateway)
    route_logs.register(app, gateway)
    route_sessions.register(app, gateway)
    route_tools.register(app, gateway)
    route_skills.register(app, gateway)
    route_workspace.register(app, gateway)
    route_scheduler.register(app, gateway)

    return app


# ═══════════════════════════════════════════════════════════════
# 视图
# ═══════════════════════════════════════════════════════════════


def _register_views(app: FastAPI, gateway: Gateway) -> None:
    """前端页面 + 组件 iframe + 静态文件。"""

    @app.get("/")
    async def index():
        """前端首页。"""
        fp = _FRONTEND_DIR / "index.html"
        if fp.is_file():
            return HTMLResponse(fp.read_text(encoding="utf-8"))
        return Response(status_code=404, content="frontend/index.html not found")

    @app.get("/s/{filename:path}")
    async def serve_static(filename: str):
        """前端静态文件（marked.min.js 等）。"""
        fp = os.path.normpath(str(_FRONTEND_DIR / filename))
        if os.path.isfile(fp) and fp.startswith(str(_FRONTEND_DIR)):
            return FileResponse(fp)
        return Response(status_code=404, content="not found")

    @app.get("/components/{tool_id}/{filename:path}")
    async def serve_component(tool_id: str, filename: str):
        """Tool 组件 iframe 文件。"""
        tool = gateway.bus.get_tool(tool_id)
        if not tool:
            return Response(status_code=404, content="tool not found")
        comp_dir = os.path.join(tool._tool_dir, "component")
        comp_path = os.path.normpath(os.path.join(comp_dir, filename))
        if not comp_path.startswith(os.path.normpath(comp_dir)):
            return Response(status_code=403, content="forbidden")
        if os.path.isfile(comp_path):
            return FileResponse(comp_path)
        return Response(status_code=404, content="component not found")


# ═══════════════════════════════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════════════════════════════


def _register_websocket(app: FastAPI, gateway: Gateway) -> None:
    """WebSocket 连接管理。"""

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(ws: WebSocket, session_id: str):
        await ws.accept()
        setattr(ws.state, "session_id", session_id)

        try:
            gateway.sessions.get_or_create(ws, session_id)
        except Exception as e:
            logger.error("websocket accept failed: session=%s", session_id)
            logger.exception(e)
            await ws.close(code=1011)
            return

        try:
            await gateway.restore_session(session_id)
            while True:
                raw = await ws.receive_text()
                data = _safe_parse_json(raw)
                if data:
                    await gateway.handle_ws_message(ws, data)
        except WebSocketDisconnect:
            logger.info("websocket disconnected: session=%s", session_id)
        except Exception as e:
            logger.error("websocket error: session=%s", session_id)
            logger.exception(e)
        finally:
            gateway.sessions.remove(session_id)


def _safe_parse_json(raw: str) -> dict | None:
    """安全解析 JSON，失败返回 None。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid JSON from frontend: %s", raw[:80])
        return None


async def start_gateway(gateway: Gateway) -> tuple:
    """启动 uvicorn 服务器。返回 (server_task, server)。"""
    import uvicorn

    app = create_app(gateway)
    config = uvicorn.Config(
        app,
        host=gateway.host,
        port=gateway.port,
        log_level="info",
        ws_max_size=10 * 1024 * 1024,
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    logger.info("gateway app started")
    return server_task, server
