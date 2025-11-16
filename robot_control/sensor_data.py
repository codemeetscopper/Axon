from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping


ROLL_CALIBRATION = 5.420720526107142
PITCH_CALIBRATION = -12.253261345
YAW_CALIBRATION = 166.39189556785712

_CALIBRATION_OFFSETS = {
    "roll": ROLL_CALIBRATION,
    "pitch": PITCH_CALIBRATION,
    "yaw": YAW_CALIBRATION,
}

ROLL_DEADBAND = 0.6
PITCH_DEADBAND = 0.6
YAW_DEADBAND = 1.0

REST_ROLL_THRESHOLD = 3.0
REST_PITCH_THRESHOLD = 3.0
REST_YAW_THRESHOLD = 4.5

REST_ROLL_DELTA_THRESHOLD = 0.5
REST_PITCH_DELTA_THRESHOLD = 0.5
REST_YAW_DELTA_THRESHOLD = 1.0

STEADY_ROLL_DELTA_THRESHOLD = 1.5
STEADY_PITCH_DELTA_THRESHOLD = 1.5
STEADY_YAW_DELTA_THRESHOLD = 2.5
STEADY_SPEED_THRESHOLD = 2.5

MAJOR_ROLL_DELTA_THRESHOLD = 6.0
MAJOR_PITCH_DELTA_THRESHOLD = 6.0
MAJOR_YAW_DELTA_THRESHOLD = 10.0
MAJOR_SPEED_DELTA_THRESHOLD = 15.0


@dataclass(slots=True)
class SensorSample:
    """Represents a single telemetry sample streamed by Axon's controller."""

    message_type: int
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
            message_type=int(data["T"]),
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
            "yaw": _apply_deadband(self.calibrated_yaw, YAW_DEADBAND),
            "pitch": _apply_deadband(self.calibrated_pitch, PITCH_DEADBAND),
            # Invert roll so that the face leans in the intuitive direction.
            "roll": _apply_deadband(-self.calibrated_roll, ROLL_DEADBAND),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SensorSample":
        """Create a sample from a dict produced by :meth:`as_dict`."""

        return cls(
            message_type=int(payload.get("message_type", payload.get("T", 0))),
            left_speed=float(payload.get("left_speed", payload.get("L", 0.0))),
            right_speed=float(payload.get("right_speed", payload.get("R", 0.0))),
            roll=float(payload.get("roll", payload.get("r", 0.0))),
            pitch=float(payload.get("pitch", payload.get("p", 0.0))),
            yaw=float(payload.get("yaw", payload.get("y", 0.0))),
            temperature_c=float(payload.get("temperature_c", payload.get("temp", 0.0))),
            voltage_v=float(payload.get("voltage_v", payload.get("v", 0.0))),
        )

    @property
    def calibrated_roll(self) -> float:
        return self.roll - _CALIBRATION_OFFSETS["roll"]

    @property
    def calibrated_pitch(self) -> float:
        return self.pitch - _CALIBRATION_OFFSETS["pitch"]

    @property
    def calibrated_yaw(self) -> float:
        return _wrap_angle(self.yaw - _CALIBRATION_OFFSETS["yaw"])

    @property
    def is_robot_frame(self) -> bool:
        return self.message_type == 1001

    def as_dict(self) -> Dict[str, Any]:
        """Expose the raw values for convenience when displaying telemetry."""

        return {
            "message_type": self.message_type,
            "left_speed": self.left_speed,
            "right_speed": self.right_speed,
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "temperature_c": self.temperature_c,
            "voltage_v": self.voltage_v,
        }

    def is_resting(
        self,
        previous_sample: "SensorSample" | None = None,
        roll_threshold: float = REST_ROLL_THRESHOLD,
        pitch_threshold: float = REST_PITCH_THRESHOLD,
        yaw_threshold: float = REST_YAW_THRESHOLD,
        roll_delta_threshold: float = REST_ROLL_DELTA_THRESHOLD,
        pitch_delta_threshold: float = REST_PITCH_DELTA_THRESHOLD,
        yaw_delta_threshold: float = REST_YAW_DELTA_THRESHOLD,
    ) -> bool:
        """Return ``True`` when the robot is within the resting orientation band."""

        roll_rest = abs(self.calibrated_roll) <= roll_threshold
        pitch_rest = abs(self.calibrated_pitch) <= pitch_threshold
        yaw_rest = abs(self.calibrated_yaw) <= yaw_threshold

        if not (roll_rest and pitch_rest and yaw_rest):
            return False

        if previous_sample is None:
            return True

        roll_delta = abs(self.calibrated_roll - previous_sample.calibrated_roll)
        pitch_delta = abs(self.calibrated_pitch - previous_sample.calibrated_pitch)
        yaw_delta = abs(_wrap_angle(self.calibrated_yaw - previous_sample.calibrated_yaw))

        return (
            roll_delta <= roll_delta_threshold
            and pitch_delta <= pitch_delta_threshold
            and yaw_delta <= yaw_delta_threshold
        )

    def is_steady(
        self,
        previous_sample: "SensorSample" | None = None,
        roll_delta_threshold: float = STEADY_ROLL_DELTA_THRESHOLD,
        pitch_delta_threshold: float = STEADY_PITCH_DELTA_THRESHOLD,
        yaw_delta_threshold: float = STEADY_YAW_DELTA_THRESHOLD,
        speed_threshold: float = STEADY_SPEED_THRESHOLD,
    ) -> bool:
        """Return ``True`` when orientation and wheel speeds barely change."""

        if previous_sample is None:
            return False

        roll_delta = abs(self.calibrated_roll - previous_sample.calibrated_roll)
        pitch_delta = abs(self.calibrated_pitch - previous_sample.calibrated_pitch)
        yaw_delta = abs(_wrap_angle(self.calibrated_yaw - previous_sample.calibrated_yaw))
        max_speed = max(abs(self.left_speed), abs(self.right_speed))
        prev_max_speed = max(abs(previous_sample.left_speed), abs(previous_sample.right_speed))

        return (
            roll_delta <= roll_delta_threshold
            and pitch_delta <= pitch_delta_threshold
            and yaw_delta <= yaw_delta_threshold
            and max_speed <= speed_threshold
            and prev_max_speed <= speed_threshold
        )

    def has_major_movement(
        self,
        previous_sample: "SensorSample" | None = None,
        roll_delta_threshold: float = MAJOR_ROLL_DELTA_THRESHOLD,
        pitch_delta_threshold: float = MAJOR_PITCH_DELTA_THRESHOLD,
        yaw_delta_threshold: float = MAJOR_YAW_DELTA_THRESHOLD,
        speed_delta_threshold: float = MAJOR_SPEED_DELTA_THRESHOLD,
    ) -> bool:
        """Return ``True`` when there is a noticeable change in orientation or speed."""

        if previous_sample is None:
            return True

        roll_delta = abs(self.calibrated_roll - previous_sample.calibrated_roll)
        pitch_delta = abs(self.calibrated_pitch - previous_sample.calibrated_pitch)
        yaw_delta = abs(_wrap_angle(self.calibrated_yaw - previous_sample.calibrated_yaw))
        max_speed_delta = max(
            abs(self.left_speed - previous_sample.left_speed),
            abs(self.right_speed - previous_sample.right_speed),
        )

        return (
            roll_delta >= roll_delta_threshold
            or pitch_delta >= pitch_delta_threshold
            or yaw_delta >= yaw_delta_threshold
            or max_speed_delta >= speed_delta_threshold
        )


def _wrap_angle(angle: float) -> float:
    """Wrap *angle* to the ``[-180, 180]`` range."""

    wrapped = (angle + 180.0) % 360.0 - 180.0
    # Account for floating point rounding that produces -180 instead of 180.
    if wrapped == -180.0 and angle > 0:
        return 180.0
    return wrapped


def _apply_deadband(value: float, threshold: float) -> float:
    """Clamp tiny variations around zero to zero to steady the face."""

    return 0.0 if abs(value) < threshold else value


def set_calibration_offsets(*, roll: float | None = None, pitch: float | None = None, yaw: float | None = None) -> None:
    """Update the calibration offsets used to normalize gyro readings."""

    if roll is not None:
        _CALIBRATION_OFFSETS["roll"] = float(roll)
    if pitch is not None:
        _CALIBRATION_OFFSETS["pitch"] = float(pitch)
    if yaw is not None:
        _CALIBRATION_OFFSETS["yaw"] = float(yaw)


def get_calibration_offsets() -> Dict[str, float]:
    """Return a copy of the current calibration offsets."""

    return dict(_CALIBRATION_OFFSETS)
