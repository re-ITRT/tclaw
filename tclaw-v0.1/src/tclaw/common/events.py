"""tclaw 事件系统 —— 核心数据结构与 Topic 定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Topic 常量 ────────────────────────────────────────────────

class Topics:
    """集中管理所有 topic 常量，避免魔法字符串。"""

    # Agent 循环
    AGENT_MESSAGE_INCOMING = "agent.message.incoming"  # 用户消息进入
    AGENT_TOOL_RESULT      = "agent.tool.result"        # tool 执行完毕返回
    AGENT_OUTPUT           = "agent.output"              # 输出给用户（前端通道消费）

    # 工具调用（动态拼接：f"{TOOL_INVOKE}.{tool_id}"）
    TOOL_INVOKE          = "tool.invoke"               # 前缀，按 tool_id 拼接

    # 系统
    SYSTEM_STARTUP   = "system.startup"
    SYSTEM_SHUTDOWN  = "system.shutdown"


# ── 事件本体 ──────────────────────────────────────────────────

@dataclass
class Event:
    """最小的消息单元，谁都能发、谁都能收。"""

    topic: str              # 事件类型，见 Topics
    payload: Any            # 携带的数据
    source: str             # 发送者标识（tool_id / agent_id 等）
    session_id: str = ""    # 所属 session，用于路由到对应队列
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展字段
