from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class SensorSample:
    """Represents a single telemetry sample streamed by Axon's controller."""

    timestamp_ms: int
    left_speed: float
    right_speed: float
    roll: float
    pitch: float
    yaw: float
    temperature_c: float
    voltage_v: float

    @classmethod
    def from_json(cls, payload: str) -> "SensorSample":
        """Create a sample from a JSON payload.

        The micro-controller sends lines that look like::

            {"T":1001,"L":0,"R":0,"r":15.58,"p":-19.38,"y":126.92,"temp":47.7,"v":12.20}

        Some firmwares prepend the line with ``"Received: "``; this method tolerates that
        automatically.
        """

        payload = payload.strip()
        if payload.startswith("Received:"):
            payload = payload.split("Received:", 1)[1].strip()

        data = json.loads(payload)
        return cls(
            timestamp_ms=int(data["T"]),
            left_speed=float(data.get("L", 0.0)),
            right_speed=float(data.get("R", 0.0)),
            roll=float(data.get("r", 0.0)),
            pitch=float(data.get("p", 0.0)),
            yaw=float(data.get("y", 0.0)),
            temperature_c=float(data.get("temp", 0.0)),
            voltage_v=float(data.get("v", 0.0)),
        )

    def to_orientation(self) -> Dict[str, float]:
        """Return a mapping compatible with :meth:`RoboticFaceWidget.set_orientation`."""

        return {
            "yaw": self.yaw,
            "pitch": self.pitch,
            "roll": self.roll,
        }

    def as_dict(self) -> Dict[str, Any]:
        """Expose the raw values for convenience when displaying telemetry."""

        return {
            "timestamp_ms": self.timestamp_ms,
            "left_speed": self.left_speed,
            "right_speed": self.right_speed,
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "temperature_c": self.temperature_c,
            "voltage_v": self.voltage_v,
        }
