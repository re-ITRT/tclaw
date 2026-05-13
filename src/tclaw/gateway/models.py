"""Gateway 消息模型与协议类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── WebSocket 消息类型常量 ───────────────────────────────────

class WsMsgType:
    """WebSocket 消息 type 枚举。"""

    # 前端 → Gateway
    TEXT = "text"                     # 用户文本消息
    TOOL_EVENT = "tool_event"         # 前端工具交互
    COMPONENT_CALLBACK = "component_callback"  # 组件回调
    CANCEL = "cancel"                 # 取消推理

    # Gateway → 前端
    ASSISTANT = "assistant"           # LLM 回复
    TOOL_RESULT = "tool_result"       # 工具结果
    COMPONENT_REGISTER = "component_register"  # 注册组件
    COMPONENT_UPDATE = "component_update"      # 更新组件
    COMPONENT_DESTROY = "component_destroy"    # 销毁组件
    ERROR = "error"                   # 错误消息


# ── 消息结构 ─────────────────────────────────────────────────


@dataclass
class WsMessage:
    """统一的 WebSocket 消息结构。"""
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""


@dataclass
class ComponentSchema:
    """前端交互组件的 schema 定义。"""
    type: str                        # input / select / confirm / file_picker
    prompt: str = ""
    placeholder: str = ""
    options: list[dict] | None = None  # select 类型用
    multiple: bool = False             # select 多选
    confirm_text: str = "确定"
    cancel_text: str = "取消"
    accept: list[str] | None = None    # file_picker 用
    multiline: bool = False            # input 多行

    def to_dict(self) -> dict:
        d = {"type": self.type}
        for k, v in self.__dict__.items():
            if v is not None and k != "type":
                d[k] = v
        return d
