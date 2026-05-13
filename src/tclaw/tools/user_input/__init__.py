"""UserInputTool —— 用户输入接收器。"""

from __future__ import annotations

import os, re, uuid
from typing import TYPE_CHECKING

from ...common.tool import Tool
from ...common.events import Topics
from ...common.settings import WORKSPACE_DIR
from ...common.conversation_logger import log_user

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

_COMPOUND_EXT_RE = re.compile(
    r"\.("
    r"tar\.(gz|bz2|xz|zst)"
    r"|7z\.\d+"
    r"|zip\.\d+"
    r"|rar\.\d+"
    r"|log\.\d+"
    r"|whl"
    r")$",
    re.IGNORECASE,
)


def smart_split_extension(filename: str) -> tuple[str, str]:
    filename = filename.strip()
    m = _COMPOUND_EXT_RE.search(filename)
    if m:
        ext = m.group()
        return filename[: -len(ext)], ext
    return os.path.splitext(filename)


def add_unique_id(filename: str, unique_id: str) -> str:
    stem, ext = smart_split_extension(filename)
    return f"{stem}-{unique_id}{ext}"


class UserInputTool(Tool):
    tool_id = "user_input"

    async def do_execute(self, payload: dict) -> None:
        """LLM 调 user_input（兼容旧路径，走 handle_gateway_event）。"""
        await self.handle_gateway_event(payload, payload.get("session_id", ""))

    async def handle_gateway_event(self, data: dict, session_id: str) -> None:
        """前端文本消息 → 触发 LLM。

        Gateway 直接调此方法，不再自己 publish 到 EventBus。
        """
        text = data.get("content", "")
        if text:
            log_user(session_id, text)
        files = data.get("files", [])
        saved_paths: list[str] = []
        if files:
            upload_dir = os.path.join(WORKSPACE_DIR, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            for f in files:
                name, file_data = f.get("name", "unknown"), f.get("data", "")
                uid = uuid.uuid4().hex[:8]
                dest = os.path.join(upload_dir, add_unique_id(name, uid))
                import base64
                try:
                    raw = base64.b64decode(file_data)
                    with open(dest, "wb") as fh:
                        fh.write(raw)
                except Exception:
                    with open(dest, "w", encoding="utf-8") as fh:
                        fh.write(file_data)
                saved_paths.append(dest)
        llm_payload: dict = {"text": text, "source": self.tool_id}
        if saved_paths:
            llm_payload["file_path"] = saved_paths
        await self.publish({
            "topic": Topics.AGENT_MESSAGE_INCOMING,
            "payload": llm_payload,
            "session_id": session_id,
        })
