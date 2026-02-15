from __future__ import annotations

import asyncio
import json
import logging
import shlex

from mcp_probe.transport.base import BaseTransport

logger = logging.getLogger(__name__)


class StdioTransport(BaseTransport):
    def __init__(self, command: str) -> None:
        self._command = command
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_chunks: list[str] = []
        self.non_json_lines: int = 0
        self.return_code: int | None = None

    @property
    def stderr_output(self) -> str:
        return "".join(self._stderr_chunks)

    async def start(self) -> None:
        args = shlex.split(self._command)
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._running = True
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def send(self, message: dict) -> None:
        if self._process is None or self._process.stdin is None:
            raise ConnectionError("Transport not started")
        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def receive(self, timeout: float) -> dict:
        return await asyncio.wait_for(self._read_line(), timeout)

    async def stop(self) -> None:
        if self._process is None:
            return
        self._running = False
        try:
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        self.return_code = self._process.returncode
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

    async def _read_line(self) -> dict:
        if self._process is None or self._process.stdout is None:
            raise ConnectionError("Transport not started")
        while True:
            raw = await self._process.stdout.readline()
            if not raw:
                raise ConnectionError("Server process closed stdout (EOF)")
            line = raw.decode().strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                self.non_json_lines += 1
                logger.debug("Non-JSON line from stdout: %s", line[:200])

    async def _read_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return
        try:
            while True:
                raw = await self._process.stderr.readline()
                if not raw:
                    break
                self._stderr_chunks.append(raw.decode())
        except asyncio.CancelledError:
            pass
