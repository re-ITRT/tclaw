"""WorkspaceManagerTool —— LLM 管理会话与工作区的工具。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.skills import discover_skills

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class WorkspaceManagerTool(Tool):
    tool_id = "workspace_manager"

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "fork", "clone"],
                "description": "list=列举 | create=创建全新 | fork=多开(共享记忆) | clone=复制(独立)",
            },
            "name": {
                "type": "string",
                "description": "操作目标名（create/clone/fork 时用）",
            },
            "source": {
                "type": "string",
                "description": "源会话（fork/clone 时用，如 main 或 sub:xxx）",
            },
            "soul": {
                "type": "string",
                "description": "人格设定（create 时可选）",
            },
            "identity": {
                "type": "string",
                "description": "身份信息（create 时可选）",
            },
            "user": {
                "type": "string",
                "description": "用户信息（create 时可选）",
            },
            "tools": {
                "type": "string",
                "description": "环境配置（create 时可选）",
            },
            "memory": {
                "type": "string",
                "description": "长期记忆（create 时可选）",
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要启用的技能列表，不传则全部启用",
            },
        },
        "required": ["action"],
    }

    async def do_execute(self, payload: dict) -> None:
        import os
        from ...common.sub_workspace import (
            list_workspaces, create_workspace, fork_workspace,
            clone_workspace,
        )
        from ...common.skills import enable_skill, disable_skill

        action = payload.get("action", "")
        sid = payload.get("session_id", "")

        if action == "list":
            workspaces = list_workspaces()
            await self.reply_to_llm({
                "status": "ok",
                "workspaces": [
                    {
                        "id": w["id"],
                        "label": w.get("label", w["id"]),
                        "kind": w["kind"],
                        "source": w.get("source"),
                    }
                    for w in workspaces
                ],
                "available_skills": discover_skills(),
            }, sid)
            return

        if action == "create":
            name = payload.get("name", "")
            if not name:
                await self.reply_to_llm({"status": "error", "message": "name required"}, sid)
                return

            session_id = f"sub:{name}"
            path = create_workspace(session_id)

            # 可选：覆盖记忆文件
            memory_files = {
                "SOUL.md": payload.get("soul"),
                "IDENTITY.md": payload.get("identity"),
                "USER.md": payload.get("user"),
                "TOOLS.md": payload.get("tools"),
                "MEMORY.md": payload.get("memory"),
            }
            ws_memory = os.path.join(path, "memory")
            for fname, content in memory_files.items():
                if content:
                    with open(os.path.join(ws_memory, fname), "w", encoding="utf-8") as f:
                        f.write(content.strip())

            # 可选：控制技能开关
            skills = payload.get("skills")
            if skills:
                all_skills = discover_skills()
                for s in all_skills:
                    if s in skills:
                        enable_skill(s)
                    else:
                        disable_skill(s)

            await self.reply_to_llm({
                "status": "ok",
                "session_id": session_id,
                "action": "created",
                "message": f"新工作区 {name} 已创建，路径 {path}",
            }, sid)
            return

        if action == "fork":
            source = payload.get("source", "main")
            name = payload.get("name", "")
            if not name:
                await self.reply_to_llm({"status": "error", "message": "name required"}, sid)
                return

            try:
                path = fork_workspace(source, name)
                await self.reply_to_llm({
                    "status": "ok",
                    "session_id": name,
                    "action": "forked",
                    "source": source,
                    "message": f"多开 {name} 已创建，共享 {source} 的记忆",
                }, sid)
            except (FileExistsError, ValueError, FileNotFoundError) as e:
                await self.reply_to_llm({"status": "error", "message": str(e)}, sid)
            return

        if action == "clone":
            source = payload.get("source", "main")
            name = payload.get("name", "")
            if not name:
                await self.reply_to_llm({"status": "error", "message": "name required"}, sid)
                return

            new_id = f"sub:{name}"
            try:
                path = clone_workspace(source, new_id)
                await self.reply_to_llm({
                    "status": "ok",
                    "session_id": new_id,
                    "action": "cloned",
                    "source": source,
                    "message": f"复制 {source} 到 {name} 完成，路径 {path}",
                }, sid)
            except (FileExistsError, FileNotFoundError) as e:
                await self.reply_to_llm({"status": "error", "message": str(e)}, sid)
            return

        await self.reply_to_llm({"status": "error", "message": f"unknown action: {action}"}, sid)
