from __future__ import annotations

import asyncio
import json
import os
import shlex
import signal
from collections import deque

from mcp_probe.protocol import MAX_MESSAGE_BYTES, ProtocolError, loads_message
from mcp_probe.transport.base import BaseTransport


class StdioTransport(BaseTransport):
    def __init__(self, command: str | list[str], *, cwd: str | None = None) -> None:
        self._command = command
        self._cwd = cwd
        self._process: asyncio.subprocess.Process | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_chunks: deque[str] = deque(maxlen=64)
        self.non_json_lines = 0
        self.return_code: int | None = None

    @property
    def stderr_output(self) -> str:
        return "".join(self._stderr_chunks)

    async def start(self) -> None:
        if self._running:
            raise RuntimeError("Transport already started")
        args = shlex.split(self._command) if isinstance(self._command, str) else self._command
        if not args:
            raise ValueError("Server command must not be empty")
        self._stderr_chunks.clear()
        self.non_json_lines = 0
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
            limit=MAX_MESSAGE_BYTES + 1,
            start_new_session=os.name == "posix",
        )
        self._running = True
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def send(self, message: dict) -> None:
        await self.send_bytes(json.dumps(message, allow_nan=False).encode() + b"\n")

    async def send_bytes(self, data: bytes) -> None:
        if not self._running or self._process is None or self._process.stdin is None:
            raise ConnectionError("Transport not started")
        if len(data) > MAX_MESSAGE_BYTES:
            raise ProtocolError("Outgoing message exceeds the byte limit")
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def receive(self, timeout: float) -> dict:
        return await asyncio.wait_for(self._read_line(), timeout)

    def _signal(self, sig: int) -> None:
        if self._process is None:
            return
        try:
            if os.name == "posix":
                os.killpg(self._process.pid, sig)
            elif self._process.returncode is None:
                self._process.terminate() if sig == signal.SIGTERM else self._process.kill()
        except ProcessLookupError:
            pass

    async def stop(self) -> None:
        self._running = False
        if self._process is None:
            return
        process = self._process
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=0.3)
        except asyncio.TimeoutError:
            self._signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self._signal(signal.SIGKILL if os.name == "posix" else signal.SIGTERM)
                await asyncio.wait_for(process.wait(), timeout=2.0)
        finally:
            # The leader can exit before children that still hold its pipe handles.
            if os.name == "posix":
                self._signal(signal.SIGKILL)
            self.return_code = process.returncode

            async def drain_stdout() -> None:
                if process.stdout is not None:
                    while await process.stdout.read(4096):
                        pass

            # Reap pipe EOF callbacks before the event loop is closed, including
            # when the leader exited while a descendant still held stdout.
            readers = [asyncio.create_task(drain_stdout())]
            if self._stderr_task is not None:
                readers.append(self._stderr_task)
            try:
                await asyncio.wait_for(asyncio.gather(*readers), 1.0)
            except asyncio.TimeoutError:
                pass
            if self._stderr_task is not None:
                self._stderr_task.cancel()
                await asyncio.gather(self._stderr_task, return_exceptions=True)
            self._process = None

    async def _read_line(self) -> dict:
        if self._process is None or self._process.stdout is None:
            raise ConnectionError("Transport not started")
        while True:
            try:
                raw = await self._process.stdout.readline()
            except ValueError as exc:
                raise ProtocolError("Stdio line exceeds the byte limit") from exc
            if not raw:
                raise ConnectionError("Server process closed stdout")
            if not raw.strip():
                continue
            try:
                return loads_message(raw)
            except ProtocolError:
                self.non_json_lines += 1
                raise

    async def _read_stderr(self) -> None:
        if self._process is None or self._process.stderr is None:
            return
        while True:
            raw = await self._process.stderr.read(4096)
            if not raw:
                return
            self._stderr_chunks.append(raw.decode(errors="replace"))
