"""ExecTool —— 执行 CLI 命令。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ...common.tool import Tool
from ...common.events import Topics

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

    async def do_execute(self, payload: dict) -> None:
        command: str = payload.get("command", "")
        workdir: str | None = payload.get("workdir")
        timeout: float | None = payload.get("timeout")
        mode: str = payload.get("mode", "return")
        if not command:
            return
        # default timeout: 60s if not specified
        if timeout is None:
            timeout = 60.0
        if mode == "no_return":
            asyncio.create_task(self._run_background(command, workdir))
            result = {"mode": "no_return", "status": "spawned"}
        else:
            result = await self._run_and_return(command, workdir, timeout)
        await self.reply_to_llm(result, payload.get("session_id", ""))

    async def _run_and_return(self, command: str, workdir: str | None, timeout: float | None) -> dict:
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
                return {"mode": "return", "status": "timeout",
                        "stdout": "", "stderr": f"Timed out after {timeout}s",
                        "exit_code": -1,
                        "duration_ms": int((time.monotonic() - start) * 1000)}
            return {"mode": "return", "status": "done",
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "exit_code": proc.returncode,
                    "duration_ms": int((time.monotonic() - start) * 1000)}
        except FileNotFoundError:
            return {"mode": "return", "status": "error",
                    "stdout": "", "stderr": f"Command not found: {command}",
                    "exit_code": -1,
                    "duration_ms": int((time.monotonic() - start) * 1000)}

    async def _run_background(self, command, workdir):
        proc = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=workdir)
        asyncio.create_task(proc.wait())
