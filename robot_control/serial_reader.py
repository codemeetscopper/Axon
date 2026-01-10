from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import serial
from serial import SerialException

from .sensor_data import SensorSample

LOGGER = logging.getLogger(__name__)


class SerialReadWriter:
    """Bidirectional serial transport that exposes reader/writer helpers."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.05,
        reconnect_delay_s: float = 1.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._reconnect_delay_s = reconnect_delay_s
        self._serial = self._open_serial()

        self._lock = threading.Lock()
        self._listeners_lock = threading.Lock()
        self._latest: Optional[SensorSample] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._closed = False
        self._error: Optional[Exception] = None
        self._line_consumers: list[Callable[[str], None]] = []
        self._init_commands = [
            '{"T": 131, "cmd": 1}',
            '{"T": 130}',
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start draining telemetry from the serial port on a dedicated thread."""

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SerialReadWriter",
            daemon=True,
        )
        self._thread.start()
        self._send_init_commands()

    def stop(self) -> None:
        """Stop the background reader and close the serial port."""

        if self._closed:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        self._close_serial()
        self._closed = True

    close = stop

    # ------------------------------------------------------------------
    # Reading + writing
    # ------------------------------------------------------------------
    def pop_latest(self) -> Optional[SensorSample]:
        """Return the latest unread sample, if one is available."""

        with self._lock:
            sample = self._latest
            self._latest = None
        return sample

    def send_command(self, command: str) -> None:
        """Send a raw command over the serial transport."""

        if self._closed:
            raise RuntimeError("Serial connection is closed")
        payload = command.rstrip("\n") + "\n"
        data = payload.encode("utf-8")
        with self._lock:
            self._serial.write(data)
            self._serial.flush()

    # ------------------------------------------------------------------
    # Diagnostics + hooks
    # ------------------------------------------------------------------
    def has_error(self) -> bool:
        return self._error is not None

    def add_line_consumer(self, consumer: Callable[[str], None]) -> None:
        """Register *consumer* to receive every decoded serial line."""

        with self._listeners_lock:
            self._line_consumers.append(consumer)

    def remove_line_consumer(self, consumer: Callable[[str], None]) -> None:
        """Remove a previously registered line consumer."""

        with self._listeners_lock:
            if consumer in self._line_consumers:
                self._line_consumers.remove(consumer)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    raw = self._serial.readline()
                except SerialException as exc:  # pragma: no cover - hardware specific
                    self._error = exc
                    LOGGER.error("Serial connection lost: %s", exc)
                    if not self._reconnect():
                        break
                    continue

                if not raw:
                    continue

                try:
                    text = raw.decode("utf-8", errors="ignore").strip()
                except UnicodeDecodeError:
                    LOGGER.debug("Skipping undecodable payload: %r", raw)
                    continue

                if not text:
                    continue

                self._dispatch_line(text)

                try:
                    sample = SensorSample.from_json(text)
                except (ValueError, KeyError) as exc:
                    LOGGER.debug("Failed to parse payload %s: %s", text, exc)
                    continue

                if not sample.is_robot_frame:
                    LOGGER.debug("Skipping non-robot frame: %s", text)
                    continue

                with self._lock:
                    self._latest = sample
        finally:
            self._stop_event.set()
            if self._error is not None and not self._closed:
                self._close_serial()
                self._closed = True

    def _dispatch_line(self, line: str) -> None:
        with self._listeners_lock:
            listeners = list(self._line_consumers)
        for consumer in listeners:
            try:
                consumer(line)
            except Exception:  # pragma: no cover - diagnostic aid
                LOGGER.exception("Serial line consumer raised an exception")

    def _close_serial(self) -> None:
        try:
            self._serial.close()
        except SerialException:  # pragma: no cover - hardware specific
            LOGGER.debug("Failed to close serial port cleanly")

    def _open_serial(self) -> serial.Serial:
        try:
            return serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=self._timeout,
            )
        except SerialException as exc:  # pragma: no cover - hardware specific
            raise RuntimeError(f"Unable to open serial port {self._port!r}: {exc}") from exc

    def _reconnect(self) -> bool:
        if self._closed or self._stop_event.is_set():
            return False
        self._close_serial()
        while not self._stop_event.is_set():
            try:
                self._serial = self._open_serial()
            except RuntimeError as exc:
                self._error = exc
                LOGGER.warning("Serial reconnect failed; retrying in %.1fs", self._reconnect_delay_s)
                self._stop_event.wait(self._reconnect_delay_s)
                continue
            self._error = None
            LOGGER.info("Serial reconnected on %s", self._port)
            self._send_init_commands()
            return True
        return False

    def _send_init_commands(self) -> None:
        for command in self._init_commands:
            try:
                self.send_command(command)
            except Exception as exc:
                LOGGER.warning("Failed to send init command %s: %s", command, exc)


class SerialReader(SerialReadWriter):
    """Backwards-compatible alias that preserves the previous API name."""

    pass
