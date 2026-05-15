"""技能管理 API 路由。

提供技能列表查询和开关控制。
技能开关控制哪些 skill 出现在 LLM 上下文菜单中。
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["skills"])


def register(app, gateway):
    """注册技能 API 路由到 FastAPI 应用。"""
    # 导入技能管理函数（非阻塞加载，避免循环依赖）
    from tclaw.common.skills import is_skill_enabled, enable_skill, disable_skill, discover_skills
    from tclaw.common.settings import SKILLS_DIR

    @app.get("/api/skills")
    async def list_skills():
        """列出所有技能及开关状态。前端 Skills 标签用。"""
        skills = []
        # 扫描 workspace/skills/ 下所有包含 SKILL.md 的目录
        for name in discover_skills():
            md_path = os.path.join(SKILLS_DIR, name, "SKILL.md")
            desc = ""
            if os.path.isfile(md_path):
                with open(md_path, encoding="utf-8") as f:
                    desc = f.read().strip()  # 完整内容，前端展开详情用
            skills.append({"id": name, "description": desc, "enabled": is_skill_enabled(name)})
        return {"skills": skills}

    @app.post("/api/skills/{name}/toggle")
    async def toggle_skill(name: str):
        """切换技能的启用/禁用。被禁用的 skill 不出现在 LLM 上下文中。"""
        # 先检查 skill 目录是否存在
        if name not in discover_skills():
            return {"status": "error", "message": f"skill not found: {name}"}
        # 翻转开关状态：禁用→启用，启用→禁用
        if is_skill_enabled(name):
            disable_skill(name)
            enabled = False
        else:
            enable_skill(name)
            enabled = True
        # 返回新状态给前端更新 toggle UI
        return {"status": "ok", "skill": name, "enabled": enabled}
