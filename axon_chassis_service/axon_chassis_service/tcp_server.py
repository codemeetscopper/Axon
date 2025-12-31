from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from .command_arbiter import CommandSource


logger = logging.getLogger(__name__)

CommandHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


@dataclass
class ClientSession:
    session_id: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    command_handler: CommandHandler
    ping_interval_s: float
    ping_timeout_s: float
    outbound: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    subscribed: bool = True
    last_pong: float = field(default_factory=time.monotonic)
    _tasks: Set[asyncio.Task] = field(default_factory=set)

    async def start(self) -> None:
        self._tasks = {
            asyncio.create_task(self._send_loop(), name=f"send-{self.session_id}"),
            asyncio.create_task(self._recv_loop(), name=f"recv-{self.session_id}"),
            asyncio.create_task(self._ping_loop(), name=f"ping-{self.session_id}"),
        }

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.writer.close()
        await self.writer.wait_closed()

    async def enqueue(self, line: str) -> None:
        await self.outbound.put(line)

    async def _send_loop(self) -> None:
        while True:
            line = await self.outbound.get()
            data = f"{line}\n".encode("utf-8")
            self.writer.write(data)
            await self.writer.drain()

    async def _recv_loop(self) -> None:
        while True:
            raw = await self.reader.readline()
            if not raw:
                raise ConnectionError("client disconnected")
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from %s: %s", self.session_id, line)
                continue
            await self._handle_message(obj)

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(self.ping_interval_s)
            await self.enqueue(json.dumps({"type": "ping"}))
            if time.monotonic() - self.last_pong > self.ping_timeout_s:
                raise TimeoutError("ping timeout")

    async def _handle_message(self, obj: Dict[str, Any]) -> None:
        msg_type = obj.get("type")
        if msg_type == "pong":
            self.last_pong = time.monotonic()
            return
        if msg_type == "ping":
            await self.enqueue(json.dumps({"type": "pong"}))
            return
        if msg_type == "subscribe":
            self.subscribed = bool(obj.get("feedback", True))
            return

        command = obj
        if msg_type == "command" and isinstance(obj.get("data"), dict):
            command = obj["data"]
        await self.command_handler(self.session_id, command)


class TcpServer(CommandSource):
    def __init__(
        self,
        host: str,
        port: int,
        max_clients: int,
        ping_interval_s: float,
        ping_timeout_s: float,
        command_handler: CommandHandler,
    ) -> None:
        self._host = host
        self._port = port
        self._max_clients = max_clients
        self._ping_interval_s = ping_interval_s
        self._ping_timeout_s = ping_timeout_s
        self._command_handler = command_handler
        self._server: Optional[asyncio.AbstractServer] = None
        self._sessions: Dict[str, ClientSession] = {}

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        logger.info("TCP server listening on %s:%s", self._host, self._port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        sessions = list(self._sessions.values())
        self._sessions.clear()
        for session in sessions:
            await session.stop()

    async def broadcast(self, line: str) -> None:
        for session in list(self._sessions.values()):
            if session.subscribed:
                await session.enqueue(line)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if len(self._sessions) >= self._max_clients:
            writer.close()
            await writer.wait_closed()
            return

        session_id = secrets.token_hex(4)
        session = ClientSession(
            session_id=session_id,
            reader=reader,
            writer=writer,
            command_handler=self._command_handler,
            ping_interval_s=self._ping_interval_s,
            ping_timeout_s=self._ping_timeout_s,
        )
        self._sessions[session_id] = session
        logger.info("Client connected: %s", session_id)

        await session.start()
        try:
            await asyncio.gather(*session._tasks)
        except Exception:
            logger.info("Client disconnected: %s", session_id)
        finally:
            await session.stop()
            self._sessions.pop(session_id, None)
