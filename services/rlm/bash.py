"""Shell execution engine for Prime RLM.

Provides async shell execution with bounded output, timeouts,
working directory persistence, background handle management, and error tracking.
"""

from __future__ import annotations
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class BashResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool = False

    @property
    def output(self) -> str:
        out = self.stdout
        if self.stderr:
            out += ("\n" if out else "") + self.stderr
        return out

    @property
    def duration(self) -> float:
        return self.duration_seconds


class BashHandle:
    """Handle for background shell processes."""

    def __init__(self, proc: asyncio.subprocess.Process, start_time: float):
        self.proc = proc
        self.start_time = start_time
        self._output_buffer = ""

    async def poll(self) -> Optional[int]:
        return self.proc.returncode

    async def kill(self):
        if self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()

    async def output(self) -> str:
        return self._output_buffer

    async def tail(self, lines: int = 20) -> str:
        all_lines = self._output_buffer.splitlines()
        return "\n".join(all_lines[-lines:])


async def bash(
    cmd: str,
    cwd: Optional[str] = None,
    timeout: float = 60.0,
    max_output_chars: int = 64 * 1024,
    env: Optional[dict[str, str]] = None
) -> BashResult:
    """Executes a shell command asynchronously and returns structured output."""
    start_time = asyncio.get_event_loop().time()
    work_dir = cwd or os.getcwd()

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    if sys.platform == "win32":
        shell_cmd = ["pwsh.exe", "-NoProfile", "-Command", cmd]
    else:
        shell_cmd = ["/bin/bash", "-c", cmd]

    try:
        proc = await asyncio.create_subprocess_exec(
            *shell_cmd,
            cwd=work_dir,
            env=full_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            timed_out = False
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            timed_out = True

        duration = asyncio.get_event_loop().time() - start_time
        stdout = stdout_bytes.decode("utf-8", errors="replace")[:max_output_chars]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:max_output_chars]

        return BashResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_seconds=duration,
            timed_out=timed_out
        )
    except Exception as exc:
        duration = asyncio.get_event_loop().time() - start_time
        return BashResult(
            stdout="",
            stderr=f"Execution error: {exc}",
            exit_code=-1,
            duration_seconds=duration,
            timed_out=False
        )
