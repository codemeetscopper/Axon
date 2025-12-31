from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, Optional


logger = logging.getLogger(__name__)

CommandSink = Callable[[Dict[str, Any]], Awaitable[None]]


class CommandSource:
    async def start(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class CommandArbiter:
    def __init__(self, command_sink: CommandSink, watchdog_timeout_s: float, stop_command: Dict[str, Any]):
        self._command_sink = command_sink
        self._watchdog_timeout_s = watchdog_timeout_s
        self._stop_command = stop_command
        self._owner_id: Optional[str] = None
        self._last_command_time: float = 0.0
        self._lock = asyncio.Lock()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog_loop(), name="watchdog")

    async def stop(self) -> None:
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            await asyncio.gather(self._watchdog_task, return_exceptions=True)
            self._watchdog_task = None

    async def submit_command(self, source_id: str, command: Dict[str, Any]) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._owner_id not in (None, source_id):
                if now - self._last_command_time > self._watchdog_timeout_s:
                    logger.warning("Command owner %s timed out; taking over", self._owner_id)
                    self._owner_id = source_id
                else:
                    logger.debug("Ignoring command from %s; owned by %s", source_id, self._owner_id)
                    return

            if self._owner_id is None:
                self._owner_id = source_id

            self._last_command_time = now

        await self._command_sink(command)

    async def _watchdog_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._watchdog_timeout_s)
            await self._inject_stop_if_stale()

    async def _inject_stop_if_stale(self) -> None:
        async with self._lock:
            if self._owner_id is None:
                return
            now = time.monotonic()
            if now - self._last_command_time <= self._watchdog_timeout_s:
                return
            logger.warning("Watchdog triggered stop for owner %s", self._owner_id)
            self._owner_id = None

        await self._command_sink(self._stop_command)
