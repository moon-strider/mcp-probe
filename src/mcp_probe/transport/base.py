from __future__ import annotations

import abc


class BaseTransport(abc.ABC):
    _running: bool = False
    protocol_version: str | None = None

    def set_tool_schemas(self, tools: list[dict]) -> None:
        """Let transports derive version-specific metadata from tool definitions."""

    @property
    def is_running(self) -> bool:
        return self._running

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def send(self, message: dict) -> None: ...

    @abc.abstractmethod
    async def receive(self, timeout: float) -> dict: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    async def __aenter__(self) -> BaseTransport:
        await self.start()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        await self.stop()
