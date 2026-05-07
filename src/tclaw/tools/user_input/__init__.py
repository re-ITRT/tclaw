"""UserInputTool —— 用户输入接收器。"""

from __future__ import annotations

import os, re, uuid
from typing import TYPE_CHECKING

from ...common.tool import Tool
from ...common.events import Event, Topics
from ...common.settings import WORKSPACE_DIR

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

    async def handle_event(self, event: Event) -> None:
        text = event.payload.get("text", "")
        files = event.payload.get("files", [])
        saved_paths: list[str] = []
        if files:
            upload_dir = os.path.join(WORKSPACE_DIR, "uploads")
            os.makedirs(upload_dir, exist_ok=True)
            for f in files:
                name, data = f.get("name", "unknown"), f.get("data", "")
                uid = uuid.uuid4().hex[:8]
                dest = os.path.join(upload_dir, add_unique_id(name, uid))
                import base64
                try:
                    raw = base64.b64decode(data)
                    with open(dest, "wb") as fh:
                        fh.write(raw)
                except Exception:
                    with open(dest, "w", encoding="utf-8") as fh:
                        fh.write(data)
                saved_paths.append(dest)
        llm_payload: dict = {"text": text}
        if saved_paths:
            llm_payload["file_path"] = saved_paths
        await self.publish(Event(
            topic=Topics.AGENT_MESSAGE_INCOMING, payload=llm_payload,
            source=self.tool_id, session_id=event.session_id,
        ))
