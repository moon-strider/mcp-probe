from __future__ import annotations

import abc
import sys

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing import TypeVar

    Self = TypeVar("Self", bound="BaseTransport")


class BaseTransport(abc.ABC):
    _running: bool = False

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

    async def __aenter__(self) -> Self:  # type: ignore[return-value]
        await self.start()
        return self  # type: ignore[return-value]

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        await self.stop()
