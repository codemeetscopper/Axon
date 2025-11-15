from __future__ import annotations

import logging
from typing import Optional

import serial
from serial import SerialException

from .sensor_data import SensorSample

LOGGER = logging.getLogger(__name__)


class SerialReader:
    """Read :class:`SensorSample` objects from a serial port."""

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

    def read_latest(self) -> Optional[SensorSample]:
        """Return the most recent sample available on the serial port.

        The micro-controller may stream data faster than the UI can refresh. To avoid
        rendering stale poses we drain the buffer and only return the most recent
        successfully parsed sample.
        """

        latest: Optional[SensorSample] = None
        try:
            while True:
                raw = self._serial.readline()
                if not raw:
                    break
                try:
                    text = raw.decode("utf-8", errors="ignore").strip()
                except UnicodeDecodeError:
                    LOGGER.debug("Skipping undecodable payload: %r", raw)
                    continue
                if not text:
                    continue
                try:
                    latest = SensorSample.from_json(text)
                except (ValueError, KeyError) as exc:
                    LOGGER.debug("Failed to parse payload %s: %s", text, exc)
        except SerialException as exc:  # pragma: no cover - hardware specific
            LOGGER.error("Serial connection lost: %s", exc)
            return None
        return latest

    def close(self) -> None:
        try:
            self._serial.close()
        except SerialException:  # pragma: no cover - hardware specific
            LOGGER.debug("Failed to close serial port cleanly")
