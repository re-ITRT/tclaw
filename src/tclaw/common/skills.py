"""Skills —— workspace skills 加载器。

两阶段加载：
  1. 菜单：提取 SKILL.md 头部的 name/description 注入 system prompt
  2. 完整加载：LLM 通过 load_skill tool 按需读取完整 SKILL.md

技能目录：SKILLS_DIR（workspace/skills/），不混入其他项目的技能。
"""

from __future__ import annotations

import os
import re

from .settings import SKILLS_DIR


# ── 技能开关状态（内存，服务重启重置） ─────────────────

_disabled_skills: set[str] = set()


def disable_skill(name: str) -> None:
    _disabled_skills.add(name)


def enable_skill(name: str) -> None:
    _disabled_skills.discard(name)


def is_skill_enabled(name: str) -> bool:
    return name not in _disabled_skills


def get_enabled_skills() -> list[str]:
    return [s for s in discover_skills() if s not in _disabled_skills]


def _parse_frontmatter(content: str) -> dict[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).strip().split("\n"):
        kv = re.split(r":\s*", line, maxsplit=1)
        if len(kv) == 2:
            meta[kv[0].strip()] = kv[1].strip().strip('"').strip("'")
    return meta


def discover_skills() -> list[str]:
    if not os.path.isdir(SKILLS_DIR):
        return []
    return sorted([
        name for name in os.listdir(SKILLS_DIR)
        if os.path.isdir(os.path.join(SKILLS_DIR, name))
        and os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md"))
    ])


def get_skill_menu() -> list[dict[str, str]]:
    """返回启用的技能菜单：name + display + 完整正文。"""
    import re
    menu = []
    for name in discover_skills():
        if name in _disabled_skills:
            continue
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        meta = _parse_frontmatter(content)
        # 去掉 YAML front matter 取正文
        body = re.sub(r"^---.*?---\n*", "", content, count=1, flags=re.DOTALL).strip()
        menu.append({
            "name": name,
            "display": meta.get("name", name),
            "description": meta.get("description", ""),
            "body": body,
        })
    return menu


def load_skill_content(folder: str) -> str:
    path = os.path.join(SKILLS_DIR, folder, "SKILL.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""
