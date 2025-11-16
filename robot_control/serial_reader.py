from __future__ import annotations

import logging
import threading
from typing import Optional, Protocol

import serial
from serial import SerialException

from .sensor_data import SensorSample

LOGGER = logging.getLogger(__name__)


class TelemetryListener(Protocol):
    def __call__(self, sample: "SensorSample", raw_payload: str) -> None:  # pragma: no cover - Protocol helper
        ...


class SerialReader:
    """Read :class:`SensorSample` objects from a serial port on a background thread."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 0.05,
    ) -> None:
        try:
            self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
        except SerialException as exc:  # pragma: no cover - hardware specific
            raise RuntimeError(f"Unable to open serial port {port!r}: {exc}") from exc

        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._latest: Optional[SensorSample] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._closed = False
        self._error: Optional[Exception] = None
        self._listeners: set[TelemetryListener] = set()

    def start(self) -> None:
        """Start draining telemetry from the serial port on a dedicated thread."""

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="SerialReader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background reader and close the serial port."""

        if self._closed:
            return

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        self._close_serial()
        self._closed = True

    def pop_latest(self) -> Optional[SensorSample]:
        """Return the latest unread sample, if one is available."""

        with self._lock:
            sample = self._latest
            self._latest = None
        return sample

    def has_error(self) -> bool:
        return self._error is not None

    def send_command(self, command: str | bytes) -> None:
        """Write a command to the serial port in a thread-safe manner."""

        if self._closed:
            raise RuntimeError("Serial connection is closed")

        if isinstance(command, str):
            payload = command.encode("utf-8")
        else:
            payload = command

        if not payload.endswith(b"\n"):
            payload += b"\n"

        with self._write_lock:
            self._serial.write(payload)
            self._serial.flush()

    def add_listener(self, listener: TelemetryListener) -> None:
        """Register *listener* to receive every parsed sample."""

        self._listeners.add(listener)

    def remove_listener(self, listener: TelemetryListener) -> None:
        self._listeners.discard(listener)

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    raw = self._serial.readline()
                except SerialException as exc:  # pragma: no cover - hardware specific
                    self._error = exc
                    LOGGER.error("Serial connection lost: %s", exc)
                    break

                if not raw:
                    continue

                try:
                    text = raw.decode("utf-8", errors="ignore").strip()
                except UnicodeDecodeError:
                    LOGGER.debug("Skipping undecodable payload: %r", raw)
                    continue

                if not text:
                    continue

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

                self._notify_listeners(sample, text)
        finally:
            self._stop_event.set()
            if self._error is not None and not self._closed:
                self._close_serial()
                self._closed = True

    def _notify_listeners(self, sample: "SensorSample", raw_payload: str) -> None:
        if not self._listeners:
            return

        for listener in list(self._listeners):
            try:
                listener(sample, raw_payload)
            except Exception:
                LOGGER.exception("Serial listener %r failed", listener)

    def _close_serial(self) -> None:
        try:
            self._serial.close()
        except SerialException:  # pragma: no cover - hardware specific
            LOGGER.debug("Failed to close serial port cleanly")

    def close(self) -> None:
        """Alias for :meth:`stop` for backwards compatibility."""

        self.stop()
