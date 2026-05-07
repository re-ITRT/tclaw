"""ExecTool —— 执行 CLI 命令。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Event, Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class ExecTool(Tool):
    tool_id = "exec"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的 shell 命令"},
            "workdir": {"type": "string", "description": "工作目录（可选）"},
            "timeout": {"type": "number", "description": "超时秒数（return 模式，可选）"},
            "mode": {
                "type": "string", "enum": ["return", "no_return"],
                "description": "return=等待结果，no_return=后台运行",
            },
        },
        "required": ["command"],
    }

    async def handle_event(self, event: Event) -> None:
        payload = event.payload
        command: str = payload.get("command", "")
        workdir: str | None = payload.get("workdir")
        timeout: float | None = payload.get("timeout")
        mode: str = payload.get("mode", "return")
        if not command:
            return
        if mode == "no_return":
            asyncio.create_task(self._run_background(command, workdir))
            result = {"tool": "exec", "mode": "no_return", "status": "spawned"}
        else:
            result = await self._run_and_return(command, workdir, timeout)
        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT, payload=result,
            source=self.tool_id, session_id=event.session_id,
        ))

    async def _run_and_return(self, command, workdir, timeout):
        import time
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=workdir)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait()
                return {"tool": "exec", "mode": "return", "status": "timeout",
                        "stdout": "", "stderr": f"Timed out after {timeout}s",
                        "exit_code": -1,
                        "duration_ms": int((time.monotonic() - start) * 1000)}
            return {"tool": "exec", "mode": "return", "status": "done",
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "exit_code": proc.returncode,
                    "duration_ms": int((time.monotonic() - start) * 1000)}
        except FileNotFoundError:
            return {"tool": "exec", "mode": "return", "status": "error",
                    "stdout": "", "stderr": f"Command not found: {command}",
                    "exit_code": -1,
                    "duration_ms": int((time.monotonic() - start) * 1000)}

    async def _run_background(self, command, workdir):
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=workdir)
        asyncio.create_task(proc.wait())
