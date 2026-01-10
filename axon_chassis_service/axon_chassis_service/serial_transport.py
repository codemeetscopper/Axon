from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import serial

from .chassis_protocol import decode_line, encode_command
from .feedback_sinks import FeedbackSink
from .utils import cancel_and_wait, create_task


logger = logging.getLogger(__name__)


class SerialTransport:
    def __init__(
        self,
        port: str,
        baudrate: int,
        reconnect_delay_s: float,
        read_timeout_s: float,
        init_commands: List[Dict[str, Any]],
        feedback_sink: FeedbackSink,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._reconnect_delay_s = reconnect_delay_s
        self._read_timeout_s = read_timeout_s
        self._init_commands = init_commands
        self._feedback_sink = feedback_sink
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="serial-transport")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def send_command(self, command: Dict[str, Any]) -> None:
        line = encode_command(command)
        await self._queue.put(line)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                serial_port = await asyncio.to_thread(
                    serial.serial_for_url,
                    self._port,
                    baudrate=self._baudrate,
                    timeout=self._read_timeout_s,
                )
            except serial.SerialException:
                logger.exception("Failed to open serial port %s", self._port)
                await asyncio.sleep(self._reconnect_delay_s)
                continue

            logger.info("Serial connected on %s", self._port)
            for command in self._init_commands:
                await self._queue.put(encode_command(command))

            reader = create_task(self._reader_loop(serial_port), "serial-reader")
            writer = create_task(self._writer_loop(serial_port), "serial-writer")

            done, pending = await asyncio.wait(
                [reader, writer],
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in done:
                if task.exception():
                    logger.error("Serial task failure", exc_info=task.exception())
            await cancel_and_wait(*pending)
            await asyncio.to_thread(serial_port.close)
            logger.warning("Serial disconnected; reconnecting")
            await asyncio.sleep(self._reconnect_delay_s)

    async def _reader_loop(self, serial_port: serial.Serial) -> None:
        while not self._stop_event.is_set():
            raw = await asyncio.to_thread(serial_port.readline)
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            obj = decode_line(line)
            if obj is None:
                logger.warning("Failed to parse serial line: %s", line)
                continue
            await self._feedback_sink.publish_feedback(obj, line)

    async def _writer_loop(self, serial_port: serial.Serial) -> None:
        while not self._stop_event.is_set():
            line = await self._queue.get()
            payload = f"{line}\n".encode("utf-8")
            try:
                await asyncio.to_thread(serial_port.write, payload)
                await asyncio.to_thread(serial_port.flush)
            except serial.SerialException:
                logger.exception("Serial write failed")
                raise
