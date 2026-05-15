"""工作区管理 API 路由。"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["workspace"])


def register(app, gateway):
    """注册工作区/模板/多开/复制相关路由。"""

    @app.get("/api/workspaces")
    async def list_workspaces():
        """列出所有工作区和模板。"""
        return {"workspaces": _ws_list()}

    @app.post("/api/workspaces/create")
    async def create_workspace(data: dict):
        """创建子工作区。"""
        sid = data.get("session_id", "")
        if not sid or not sid.startswith("sub:"):
            return {"status": "error", "message": "must start with 'sub:'"}
        return _ws_create(sid)

    @app.post("/api/workspaces/{name}/clone")
    async def clone_workspace(name: str, data: dict):
        """完全拷贝一份独立工作区。"""
        new_id = data.get("new_id", "")
        if not new_id:
            return {"status": "error", "message": "new_id required"}
        return _ws_clone(name, new_id)

    @app.post("/api/workspaces/{name}/fork")
    async def fork_workspace(name: str, data: dict):
        """多开，共享记忆。"""
        new_id = data.get("new_id", name)
        return _ws_fork(name, new_id)

    @app.post("/api/workspaces/{name}/template")
    async def create_template(name: str, data: dict):
        """从 session 导出为模板。"""
        tmpl_name = data.get("template_name", "") or name
        return _ws_template(name, tmpl_name)

    @app.post("/api/workspaces/from-template")
    async def from_template(data: dict):
        """从模板创建新工作区。"""
        tmpl = data.get("template", "")
        new_id = data.get("new_id", "")
        if not tmpl or not new_id:
            return {"status": "error", "message": "template and new_id required"}
        return _ws_from_template(tmpl, new_id)

    @app.delete("/api/workspaces/{name}")
    async def delete_workspace(name: str):
        """删除工作区或 fork 映射。main 不可删。"""
        from tclaw.common.sub_workspace import delete_workspace as _del
        return {"status": "deleted" if _del(name) else "error", "name": name}


# ═══════════════════════════════════════════════════════════════
# 辅助函数（降低 register 函数复杂度）
# ═══════════════════════════════════════════════════════════════


def _get_ws():
    """延迟导入 sub_workspace 模块。"""
    from tclaw.common.sub_workspace import (
        list_workspaces, create_workspace, clone_workspace,
        fork_workspace, create_template, use_template,
    )
    return list_workspaces, create_workspace, clone_workspace, fork_workspace, create_template, use_template


def _ws_list():
    """列出工作区。"""
    return _get_ws()[0]()


def _ws_create(sid: str):
    """创建子工作区（带错误处理）。"""
    try:
        return {"status": "ok", "session_id": sid, "path": _get_ws()[1](sid)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _ws_clone(name: str, new_id: str):
    """复制工作区（带错误处理）。"""
    try:
        return {"status": "ok", "session_id": new_id, "path": _get_ws()[2](name, new_id)}
    except (FileExistsError, FileNotFoundError) as e:
        return {"status": "error", "message": str(e)}


def _ws_fork(name: str, new_id: str):
    """多开工作区（带错误处理）。"""
    try:
        return {"status": "ok", "session_id": new_id, "path": _get_ws()[3](name, new_id)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _ws_template(name: str, tmpl_name: str):
    """创建模板（带错误处理）。"""
    try:
        return {"status": "ok", "template": tmpl_name, "path": _get_ws()[4](name, tmpl_name)}
    except (FileExistsError, FileNotFoundError) as e:
        return {"status": "error", "message": str(e)}


def _ws_from_template(tmpl: str, new_id: str):
    """从模板创建（带错误处理）。"""
    try:
        path = _get_ws()[5](tmpl, new_id)
        return {"status": "ok", "session_id": new_id, "path": path, "template": tmpl}
    except Exception as e:
        return {"status": "error", "message": str(e)}
