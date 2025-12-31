from __future__ import annotations

import abc
import asyncio
import logging
from typing import Iterable, List


logger = logging.getLogger(__name__)


class FeedbackSink(abc.ABC):
    @abc.abstractmethod
    async def publish_feedback(self, obj: dict, raw_line: str) -> None:
        """Consume feedback frames from the chassis."""


class NullSink(FeedbackSink):
    async def publish_feedback(self, obj: dict, raw_line: str) -> None:
        return None


class FanoutSink(FeedbackSink):
    def __init__(self, sinks: Iterable[FeedbackSink]):
        self._sinks: List[FeedbackSink] = list(sinks)

    async def publish_feedback(self, obj: dict, raw_line: str) -> None:
        await asyncio.gather(
            *(sink.publish_feedback(obj, raw_line) for sink in self._sinks),
            return_exceptions=True,
        )


class TcpBroadcastSink(FeedbackSink):
    def __init__(self, tcp_server: "TcpServer"):
        self._tcp_server = tcp_server

    async def publish_feedback(self, obj: dict, raw_line: str) -> None:
        await self._tcp_server.broadcast(raw_line)


# Deferred import for type checking.
from .tcp_server import TcpServer  # noqa: E402
