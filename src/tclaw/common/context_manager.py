"""ContextManager —— 对话上下文管理器。

上下文分四个区块，按可变性从低到高排列：

  块1 — 系统初始化（几乎不变）
    ├─ SOUL.md（最前面，每个 session 都加载）
    ├─ 人格/身份/用户/环境（USER/IDENTITY/TOOLS.md）
    └─ MEMORY.md + 今日/昨日笔记（仅 main session）

  块2 — 已加载技能（加载后不变，放对话前提高命中率）
        load_skill 注入的完整 SKILL.md 内容

  块3 — 对话区（持续增长）
        user/assistant/tool 消息

  块4 — 技能菜单（每次重建，动态更新）
        可用 skill 列表
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from datetime import date, timedelta

from .settings import (
    WORKSPACE_DIR,
    MEMORY_DIR,
    MEMORY_DAILY_DIR,
    SESSION_DIR,
    AGENT_SOUL,
    AGENT_IDENTITY,
    AGENT_USER,
    AGENT_TOOLS,
    SKILLS_DIR,
    GATEWAY_HOST,
    GATEWAY_PORT,
    LLM_MODEL,
    SUB_WORKSPACES_DIR,
)
from .skills import get_skill_menu
from .sub_workspace import get_workspace_path, create_workspace, _get_forks


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


def _get_memory_dir(session_id: str = "") -> str:
    """获取 session 对应的 memory 目录。支持 fork 映射。"""
    if not session_id or session_id == "main":
        return MEMORY_DIR

    forks = _get_forks()

    # fork 映射：共享源工作区记忆
    if session_id in forks:
        source = forks[session_id]
        if source == "main":
            return MEMORY_DIR
        return os.path.join(SUB_WORKSPACES_DIR, source, "memory")

    # sub: 子工作区
    if session_id.startswith("sub:"):
        ws = get_workspace_path(session_id)
        if not ws or not os.path.isdir(ws):
            create_workspace(session_id)
            ws = get_workspace_path(session_id)
        return os.path.join(ws, "memory")

    return MEMORY_DIR


def _build_init_prompt(session_type: str = "main", session_id: str = "") -> str:
    """块1 — 系统初始化。

    根据 session_id 加载对应子工作区的记忆文件。
    """
    parts = []

    # 确定 memory 目录
    memory_dir = _get_memory_dir(session_id)
    soul_path = os.path.join(memory_dir, "SOUL.md")
    identity_path = os.path.join(memory_dir, "IDENTITY.md")
    user_path = os.path.join(memory_dir, "USER.md")
    tools_path = os.path.join(memory_dir, "TOOLS.md")

    # 2. 工作区与环境信息
    env_lines = [
        f"工作区路径: {WORKSPACE_DIR}",
        f"会话目录: {SESSION_DIR}",
        f"记忆目录: {MEMORY_DIR}",
        f"技能目录: {SKILLS_DIR}",
        f"Gateway 监听: {GATEWAY_HOST}:{GATEWAY_PORT}",
        f"LLM 模型: {LLM_MODEL}",
    ]
    parts.append(f"## 环境\n\n" + "\n".join(env_lines))

    # 3. 身份/用户/自定义配置
    for label, path in [
        ("身份", identity_path),
        ("用户", user_path),
        ("工具", tools_path),
    ]:
        content = _read_file(path)
        if content:
            parts.append(f"## {label}\n\n{content}")

    # 3. 记忆 + 每日笔记
    memory = _read_file(os.path.join(memory_dir, "MEMORY.md"))
    if memory:
        parts.append(f"## 长期记忆\n\n{memory}")

    # 今天 + 昨天的每日笔记
    today = date.today()
    for d in [today, today - timedelta(days=1)]:
        daily_path = os.path.join(memory_dir, "daily", f"{d.isoformat()}.md")
        content = _read_file(daily_path)
        if content:
            parts.append(f"## 每日笔记 ({d.isoformat()})\n\n{content}")

    # 引导文件已全部注入上下文，无需再读
    parts.append(
        "## 注意\n\n"
        "SOUL.md、MEMORY.md、IDENTITY.md、USER.md、TOOLS.md 等引导文件"
        "已全部加载到本 system prompt 中。\n"
        "**不要使用 read/edit/memory_get 等工具读取这些文件**"
        "——内容就在这里。\n\n"
        "## 跨 session 通信\n\n"
        "当消息以 `[from session {id}]` 开头时，说明是其他 session 发来的。\n"
        "\n"
        "回复方法：\n"
        "1. 从消息前缀中提取对方的 session ID（{id} 的值）\n"
        "2. 调用 `cross_session(target_session=\"{id}\", content=\"你的回复\")`\n"
        "\n"
        "**一般情况下请回复对方**，除非：\n"
        "- 对方只是通知性消息，不需要回应\n"
        "- 你已经回复过同一话题，避免无限循环\n"
        "- 对方明确说了不需要回复\n"
        "\n"
        "示例：收到 `[from session main] 同志你好！` → `cross_session(target_session=\"main\", content=\"同志你好！\")`\n"
        "如果只是确认收到，回复一句简单的确认即可。\n\n"
        "## 回复格式\n\n"
        "所有回复使用 **Markdown** 格式。"
        "支持：标题、粗体、列表、代码块、表格、链接等。"
        "这能让前端正确渲染格式。"
    )
    return "\n\n".join(parts)


def _build_skills_block() -> str:
    """块4 — 技能菜单（只含 name/description，动态更新）。"""
    items = get_skill_menu()
    if not items:
        return ""
    lines = ["## 可用技能", "", "当用户的任务需要用到某个技能时，调用 `load_skill` 加载完整内容。", ""]
    for sk in items:
        desc = sk["description"]
        if desc:
            lines.append(f"- `{sk['name']}` — {desc}")
        else:
            lines.append(f"- `{sk['name']}`")
    if items:
        lines.append("")
        lines.append("用法：`load_skill(name=技能名称)` — 将完整 SKILL.md 注入上下文。")
    return "\n".join(lines)


def _truncate_history(messages: list[dict], max_messages: int = 50) -> list[dict]:
    if len(messages) <= max_messages:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    kept = rest[-(max_messages - len(system)):]
    return system + kept


class ContextManager:
    def __init__(self, system_prompt: str = "", session_type: str = "main",
                 session_id: str = "") -> None:
        self._system_prompt = system_prompt
        self._session_type = session_type
        self._session_id = session_id
        self._init_prompt = _build_init_prompt(session_type, session_id)
        self._prelude: list[dict] = []
        self._history: list[dict] = []
        self._last_tool_call_ids: list[str] = []
        self._load()  # 从磁盘加载持久化状态

    async def build_context(
        self,
        new_event: dict | None = None,
        tool_result: dict | None = None,
        tool_specs: list[dict] | None = None,
    ) -> Context:
        """构建上下文。所有 system 内容合并为一个长 message，减少 JSON 开销。"""
        ctx = Context()
        parts: list[str] = []

        # ── 块1：系统初始化 ──────────────────────────
        if self._init_prompt:
            parts.append(self._init_prompt)

        # ── 块2：已加载技能 ──────────────────────────
        for msg in self._prelude:
            content = msg.get("content", "").strip()
            if content:
                parts.append(content)

        if parts:
            ctx.messages.append({"role": "system", "content": "\n\n".join(parts)})

        # ── 块3：对话区 ──────────────────────────────
        ctx.messages.extend(self._history)

        # ── 块4：技能菜单（放对话后面，最靠近 LLM 回复） ─
        skills_content = _build_skills_block()
        if skills_content:
            ctx.messages.append({"role": "system", "content": skills_content})

        if new_event:
            text = new_event.get("content", "")
            file_paths = new_event.get("file_path", [])
            from_sid = new_event.get("from_session_id", "")
            text_parts = []
            if from_sid:
                text_parts.append(f"[from session {from_sid}]")
            if text:
                text_parts.append(text)
            if file_paths:
                text_parts.append(f"file_path:{file_paths}")
            ctx.messages.append({
                "role": new_event.get("role", "user"),
                "content": "\n".join(text_parts),
            })
        elif tool_result:
            tool_msg = {"role": "tool", "content": str(tool_result)}
            if self._last_tool_call_ids:
                tool_msg["tool_call_id"] = self._last_tool_call_ids.pop(0)
            else:
                # 保底：从 tool_result 中提取 tool_call_id
                tid = ""
                if isinstance(tool_result, dict):
                    tid = tool_result.get("tool_call_id", "")
                if not tid:
                    tid = tool_result.get("id", "") if isinstance(tool_result, dict) else ""
                if not tid:
                    tid = "call_unknown"
                tool_msg["tool_call_id"] = tid
            ctx.messages.append(tool_msg)

        if tool_specs:
            ctx.tools = tool_specs

        return ctx

    async def append(self, message: dict) -> None:
        self._history.append(message)
        self._save()

    def add_to_prelude(self, role: str, content: str) -> None:
        self._prelude.append({"role": role, "content": content})
        self._save()

    def _session_path(self) -> str:
        import os as _os
        return _os.path.join(SESSION_DIR, f"{self._session_id}.json") if self._session_id else ""

    def _save(self) -> None:
        path = self._session_path()
        if not path:
            return
        import json, os as _os
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "prelude": self._prelude,
                "history": self._history,
                "last_tool_call_ids": self._last_tool_call_ids,
            }, f, ensure_ascii=False, indent=2)

    def _load(self) -> None:
        path = self._session_path()
        if not path:
            return
        import json, os as _os
        if not _os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._prelude = data.get("prelude", [])
            self._history = data.get("history", [])
            self._last_tool_call_ids = data.get("last_tool_call_ids", [])
        except Exception:
            pass

    async def clear(self) -> None:
        """清空所有历史并删除持久化文件。"""
        self._history.clear()
        self._prelude.clear()
        self._last_tool_call_ids.clear()
        import os as _os
        path = self._session_path()
        if path and _os.path.isfile(path):
            _os.remove(path)

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    async def truncate(self, max_messages: int = 50) -> int:
        before = len(self._history)
        truncated = _truncate_history(self._history, max_messages)
        self._history = truncated
        return before - len(self._history)

    async def compact(self, llm: Any, keep_recent: int = 20000, user_prompt: str = "") -> str:
        """压缩早期对话历史，保留最近的消息。

        Parameters
        ----------
        llm : LLMClient
        keep_recent : int
            保留的最近 token 数（估算），之前的消息被压缩。

        Returns
        -------
        str — 生成的摘要
        """
        if not self._history:
            return ""

        # 1. 保留最近消息，找到截断点
        # 粗略估算：1 token ≈ 2 chars，每消息额外 50 token 开销
        recent_tokens = 0
        split_idx = len(self._history)
        for i in range(len(self._history) - 1, -1, -1):
            m = self._history[i]
            text = str(m.get("content", ""))
            tool_calls = m.get("tool_calls")
            tokens = len(text) // 2 + 50
            if tool_calls:
                tokens += len(tool_calls) * 30
            recent_tokens += tokens
            if recent_tokens > keep_recent:
                split_idx = i + 1
                break

        to_compress = self._history[:split_idx]
        to_keep = self._history[split_idx:]

        if not to_compress:
            return ""  # 没有需要压缩的

        # 2. 归档原始历史
        import json, os
        from datetime import datetime
        from .settings import SESSION_DIR
        archive_dir = os.path.join(SESSION_DIR, "archives")
        os.makedirs(archive_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(archive_dir, f"{self._session_id}_{ts}.json")
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump({"prelude": self._prelude, "history": to_compress}, f,
                      ensure_ascii=False, indent=2)

        # 3. 构建压缩摘要
        history_text = ""
        for m in to_compress:
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:2000]
            if m.get("tool_calls"):
                tc_names = [tc.get("function", {}).get("name", "?") for tc in m["tool_calls"]]
                content += f" [called tools: {', '.join(tc_names)}]"
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
        )
        if user_prompt:
            prompt += f"## 用户指示\n{user_prompt}\n\n"
        prompt += "## 压缩结果\n"

        response = await llm.chat([
            {"role": "system", "content": "你是对话压缩专家。保留关键信息，输出简洁摘要。"},
            {"role": "user", "content": prompt},
        ])

        summary = response.text.strip() or "(压缩摘要为空)"

        # 4. 替换历史：摘要 + Understood + 保留的最近消息
        self._history = [
            {"role": "system", "content": f"## 对话摘要\n\n{summary}"},
            {"role": "assistant", "content": "Understood, continue."},
        ] + to_keep

        self._save()
        return summary
