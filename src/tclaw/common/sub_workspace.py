"""SubWorkspace —— 子工作区管理。

每个 session 可以拥有独立的记忆空间（MEMORY.md、USER.md 等），
存储在 workspace/sub_workspaces/sub:{name}/ 目录下。

多开（fork）：通过 forks.json 注册映射，多个 session 共享同一套记忆文件
复制（clone）：拷贝一份新的独立记忆

模板：workspace/sub_workspaces/template:{name}/ 作为模板来源
"""

from __future__ import annotations

import json
import os
import shutil

from .settings import SUB_WORKSPACES_DIR, MEMORY_DIR


_FORKS_FILE: str = ""


def _ensure_dir() -> None:
    os.makedirs(SUB_WORKSPACES_DIR, exist_ok=True)


def _get_forks() -> dict[str, str]:
    """读取 fork 映射表。{forked_id: source_id}"""
    global _FORKS_FILE
    if not _FORKS_FILE:
        _FORKS_FILE = os.path.join(SUB_WORKSPACES_DIR, ".forks.json")
    if os.path.isfile(_FORKS_FILE):
        try:
            with open(_FORKS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_forks(forks: dict[str, str]) -> None:
    with open(_FORKS_FILE, "w") as f:
        json.dump(forks, f, indent=2)


def list_workspaces() -> list[dict]:
    """列出所有子工作区和模板。始终包含 main。"""
    _ensure_dir()
    entries = [{
        "id": "main",
        "label": "main",
        "kind": "session",
        "path": MEMORY_DIR,
        "source": None,
    }]
    for name in sorted(os.listdir(SUB_WORKSPACES_DIR)):
        full = os.path.join(SUB_WORKSPACES_DIR, name)
        if not os.path.isdir(full):
            continue
        if name.startswith("sub:"):
            entries.append({
                "id": name,
                "label": name[4:],
                "kind": "session",
                "path": full,
                "source": None,
            })
        elif name.startswith("template:"):
            entries.append({
                "id": name,
                "label": name[9:],
                "kind": "template",
                "path": full,
            })

    # 多开（fork）映射 - 显示为独立 session
    forks = _get_forks()
    for fid, source in forks.items():
        entries.append({
            "id": fid,
            "label": fid,
            "kind": "fork",
            "path": _resolve_fork_path(fid, source),
            "source": source,
        })

    return entries


def _resolve_fork_path(fork_id: str, source_id: str) -> str:
    """获取 fork session 对应的 memory 目录路径。"""
    if source_id == "main":
        return MEMORY_DIR
    return os.path.join(SUB_WORKSPACES_DIR, source_id, "memory")


def get_workspace_path(session_id: str) -> str:
    """获取 session 对应的工作区路径。支持 fork 映射和 sub: 子工作区。"""
    if session_id == "main":
        return ""

    # fork 映射
    if _FORKS_FILE and os.path.isfile(_FORKS_FILE):
        forks = _get_forks()
        if session_id in forks:
            source = forks[session_id]
            if source == "main":
                return ""
            return os.path.join(SUB_WORKSPACES_DIR, source)

    # sub: 子工作区
    if session_id.startswith("sub:"):
        return os.path.join(SUB_WORKSPACES_DIR, session_id)

    return ""


def create_workspace(session_id: str) -> str:
    """创建 session 的子工作区。"""
    _ensure_dir()
    ws_path = os.path.join(SUB_WORKSPACES_DIR, session_id)
    if os.path.isdir(ws_path):
        return ws_path
    os.makedirs(os.path.join(ws_path, "memory"), exist_ok=True)
    os.makedirs(os.path.join(ws_path, "daily"), exist_ok=True)

    # 从根工作区的 memory 复制模板文件（如果存在）
    for fname in ["MEMORY.md", "USER.md", "IDENTITY.md", "SOUL.md", "TOOLS.md"]:
        src = os.path.join(MEMORY_DIR, fname)
        dst = os.path.join(ws_path, "memory", fname)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst)

    return ws_path


def clone_workspace(source_id: str, new_id: str) -> str:
    """复制工作区：完全拷贝一份独立的。支持从 main 克隆。"""
    _ensure_dir()
    dst = os.path.join(SUB_WORKSPACES_DIR, new_id)
    if os.path.isdir(dst):
        raise FileExistsError(f"workspace already exists: {new_id}")
    if source_id == "main":
        # 从根 memory 目录克隆到新 sub-workspace
        os.makedirs(os.path.join(dst, "memory"), exist_ok=True)
        for fname in os.listdir(MEMORY_DIR):
            src_file = os.path.join(MEMORY_DIR, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, os.path.join(dst, "memory", fname))
        return dst
    src = os.path.join(SUB_WORKSPACES_DIR, source_id)
    if not os.path.isdir(src):
        raise FileNotFoundError(f"workspace not found: {source_id}")
    shutil.copytree(src, dst)
    return dst


def fork_workspace(source_id: str, new_id: str) -> str:
    """多开：新建 session，共享原工作区的记忆文件。

    不在 sub_workspaces 创建目录，仅在 .forks.json 注册映射。
    session 名字用户自己填，不强制 sub: 前缀。
    """
    _ensure_dir()
    if not new_id or new_id == "main":
        raise ValueError(f"invalid fork id: {new_id}")

    # 注册 fork 映射
    forks = _get_forks()
    if new_id in forks:
        raise FileExistsError(f"fork already exists: {new_id}")
    forks[new_id] = source_id
    _save_forks(forks)
    return _resolve_fork_path(new_id, source_id)


def delete_workspace(session_id: str) -> bool:
    """删除子工作区或 fork 映射。main 不可删。"""
    if session_id == "main":
        return False

    # fork 映射
    forks = _get_forks()
    if session_id in forks:
        del forks[session_id]
        _save_forks(forks)
        return True

    # sub: 子工作区
    if session_id.startswith("sub:"):
        ws_path = os.path.join(SUB_WORKSPACES_DIR, session_id)
        if os.path.isdir(ws_path):
            shutil.rmtree(ws_path)
            return True
        return False

    return False


def use_template(template_name: str, new_id: str) -> str:
    """从模板创建新工作区。应用保存的技能配置。"""
    import json
    src = os.path.join(SUB_WORKSPACES_DIR, f"template:{template_name}")
    if not os.path.isdir(src):
        raise FileNotFoundError(f"template not found: {template_name}")
    path = clone_workspace(f"template:{template_name}", new_id)

    # 应用技能配置
    skills_config = os.path.join(src, "skills.json")
    if os.path.isfile(skills_config):
        try:
            from .skills import enable_skill, disable_skill
            with open(skills_config, "r") as f:
                config = json.load(f)
            for skill_name, enabled in config.items():
                if enabled:
                    enable_skill(skill_name)
                else:
                    disable_skill(skill_name)
        except Exception:
            pass

    return path


def _resolve_source_memory_dir(source_id: str) -> str:
    """获取源 session 的 memory 目录。"""
    if source_id == "main":
        return MEMORY_DIR
    # fork 映射
    forks = _get_forks()
    if source_id in forks:
        src = forks[source_id]
        if src == "main":
            return MEMORY_DIR
        return os.path.join(SUB_WORKSPACES_DIR, src, "memory")
    # sub: 子工作区
    if source_id.startswith("sub:"):
        return os.path.join(SUB_WORKSPACES_DIR, source_id, "memory")
    return MEMORY_DIR


def create_template(source_id: str, template_name: str) -> str:
    """从 session 创建模板：复制记忆 + 保存技能配置。"""
    _ensure_dir()
    dst = os.path.join(SUB_WORKSPACES_DIR, f"template:{template_name}")
    if os.path.isdir(dst):
        raise FileExistsError(f"template already exists: {template_name}")

    # 复制记忆文件
    src_memory = _resolve_source_memory_dir(source_id)
    dst_memory = os.path.join(dst, "memory")
    os.makedirs(dst_memory, exist_ok=True)
    if os.path.isdir(src_memory):
        for fname in os.listdir(src_memory):
            src_file = os.path.join(src_memory, fname)
            if os.path.isfile(src_file):
                shutil.copy2(src_file, dst_memory)

    # 保存技能配置
    from .skills import discover_skills, is_skill_enabled
    skill_config = {
        s: is_skill_enabled(s)
        for s in discover_skills()
    }
    if skill_config:
        import json
        with open(os.path.join(dst, "skills.json"), "w") as f:
            json.dump(skill_config, f, indent=2)

    return dst
