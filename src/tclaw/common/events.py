"""tclaw 事件系统 —— Topic 常量 + 事件构造。

事件格式统一为 dict：{"topic": str, "payload": dict}

payload 约定包含 session_id、source 等字段。
"""

from __future__ import annotations

from typing import Any


# ── Topic 常量 ────────────────────────────────────────────────

class Topics:
    """集中管理所有 topic 常量。"""

    # Agent 循环
    AGENT_MESSAGE_INCOMING = "agent.message.incoming"
    AGENT_TOOL_RESULT      = "agent.tool.result"
    AGENT_OUTPUT           = "agent.output"

    # 工具调用（前缀，按 tool_id 拼接）
    #   完整 topic: tool.invoke.{id}
    #   生命周期:   tool.invoke.{id}:before  /  :after
    TOOL_INVOKE = "tool.invoke"

    # 网关
    GATEWAY_MESSAGE_INCOMING = "gateway.message.incoming"

    # 系统
    SYSTEM_STARTUP   = "system.startup"
    SYSTEM_SHUTDOWN  = "system.shutdown"
