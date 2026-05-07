"""ContextManager —— 对话上下文管理器。

Skill 热加载：每次 build_context 重新读取 skills/，新增 skill 即时生效。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .settings import (
    WORKSPACE_DIR,
    AGENT_SOUL,
    AGENT_IDENTITY,
    AGENT_USER,
    AGENT_TOOLS,
)
from .skills import get_skill_menu
from .skills import load_skill_content  # noqa: F401


@dataclass
class Context:
    messages: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)


def _read_file(path: str) -> str:
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def _build_base_prompt(base: str) -> str:
    """组装 base prompt（不含 skills，缓存用）。"""
    parts = [base] if base else []
    for label, path in [
        ("人格", AGENT_SOUL),
        ("身份", AGENT_IDENTITY),
        ("用户", AGENT_USER),
        ("环境", AGENT_TOOLS),
    ]:
        content = _read_file(path)
        if content:
            parts.append(f"## {label}\n\n{content}")
    return "\n\n".join(parts)


def _build_skills_menu() -> str:
    """热加载 skill 菜单（仅 name/description，~100 tokens）。"""
    items = get_skill_menu()
    if not items:
        return ""
    lines = ["## 可用技能"]
    for sk in items:
        display = sk["display"]
        desc = sk["description"]
        if desc:
            lines.append(f"- {sk['name']} ({display}): {desc}")
        else:
            lines.append(f"- {sk['name']} ({display})")
    lines.append("用 load_skill 工具加载完整内容。")
    return "\n".join(lines)


def _truncate_history(messages: list[dict], max_messages: int = 50) -> list[dict]:
    if len(messages) <= max_messages:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    kept = rest[-(max_messages - len(system)):]
    return system + kept


class ContextManager:
    def __init__(self, system_prompt: str = "") -> None:
        self._base_prompt = _build_base_prompt(system_prompt)
        self._prelude: list[dict] = []  # skill 等前置内容，在历史之前
        self._history: list[dict] = []

    def _build_full_system_prompt(self) -> str:
        """每次调用组合 base（缓存）+ skills（热加载）+ 能力概览。"""
        parts = [self._base_prompt] if self._base_prompt else []

        skills = _build_skills_menu()
        if skills:
            parts.append(skills)

        parts.append(
            "## 能力\n\n"
            "可用工具见 function-calling 定义。\n"
            "完成任务后调用 output(mode='end') 结束本轮对话。"
        )
        return "\n\n".join(parts)

    async def build_context(
        self,
        new_event: dict | None = None,
        tool_result: dict | None = None,
        tool_specs: list[dict] | None = None,
    ) -> Context:
        ctx = Context()

        sys_prompt = self._build_full_system_prompt()
        if sys_prompt:
            ctx.messages.append({"role": "system", "content": sys_prompt})

        ctx.messages.extend(self._prelude)   # 技能等前置内容
        ctx.messages.extend(self._history)   # 对话历史

        if new_event:
            text = new_event.get("content", "")
            file_paths = new_event.get("file_path", [])
            from_sid = new_event.get("from_session_id", "")
            parts = []
            if from_sid:
                parts.append(f"[来自 session {from_sid}]")
            if text:
                parts.append(text)
            if file_paths:
                parts.append(f"file_path:{file_paths}")
            ctx.messages.append({
                "role": new_event.get("role", "user"),
                "content": "\n".join(parts),
            })
        elif tool_result:
            ctx.messages.append({"role": "tool", "content": str(tool_result)})

        if tool_specs:
            ctx.tools = tool_specs

        return ctx

    async def append(self, message: dict) -> None:
        self._history.append(message)

    def add_to_prelude(self, role: str, content: str) -> None:
        """向前置区域添加内容（skill 注入等）。"""
        self._prelude.append({"role": role, "content": content})

    async def clear(self) -> None:
        self._history.clear()

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    async def truncate(self, max_messages: int = 50) -> int:
        before = len(self._history)
        sys_prompt = self._build_full_system_prompt()
        sys_msg = [{"role": "system", "content": sys_prompt}] if sys_prompt else []
        truncated = _truncate_history(sys_msg + self._history, max_messages)
        self._history = [m for m in truncated if m.get("role") != "system"]
        return before - len(self._history)

    async def compact(self, llm: Any) -> str:
        """用 LLM 压缩对话历史。保留 prelude，将 history 浓缩为一段摘要。

        Parameters
        ----------
        llm : LLMClient
            用于压缩的 LLM 客户端（通常与主循环同模型）

        Returns
        -------
        str
            压缩摘要文本
        """
        if not self._history:
            return ""

        # 构建压缩 prompt
        history_text = ""
        for m in self._history:
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:2000]
            if m.get("tool_calls"):
                content += f" [called tool: {m['tool_calls'][0].get('function', {}).get('name', '?')}]"
            history_text += f"[{role}] {content}\n\n"

        prelude_text = ""
        for m in self._prelude:
            content = str(m.get("content", ""))[:500]
            prelude_text += f"{content}\n\n"

        prompt = (
            "压缩以下对话历史，保留所有关键信息（决策、结果、工具调用、用户意图）。\n"
            "输出精炼的摘要，用对话口吻，保留所有文件名、路径、ID、数值。\n\n"
            f"## 前置上下文（保留）\n{prelude_text}\n"
            f"## 待压缩的对话\n{history_text}\n"
            "## 压缩结果\n"
        )

        response = await llm.chat([
            {"role": "system", "content": "你是对话压缩专家。压缩对话，保留关键信息。"},
            {"role": "user", "content": prompt},
        ])

        summary = response.text.strip() or "(压缩摘要为空)"

        # 替换 history 为压缩后的版本
        self._history = [
            {"role": "system", "content": f"## 历史摘要\n\n{summary}"},
        ]

        return summary
