from __future__ import annotations

from dataclasses import dataclass

from robot_control.sensor_data import SensorSample

from .controller import PanTiltController


@dataclass(slots=True)
class GimbalConfig:
    neutral_pan: float = 90.0
    neutral_tilt: float = 90.0
    max_pan_offset: float = 45.0
    max_tilt_offset: float = 45.0
    yaw_gain: float = 1.0
    pitch_gain: float = 1.0
    smoothing: float = 0.2


class PanTiltGimbalController:
    """Translate IMU samples into pan/tilt stabilization commands."""

    def __init__(self, controller: PanTiltController, config: GimbalConfig | None = None) -> None:
        self._controller = controller
        self._config = config or GimbalConfig()
        self._pan = self._config.neutral_pan
        self._tilt = self._config.neutral_tilt

    def close(self) -> None:
        self._controller.close()

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def apply_sample(self, sample: SensorSample) -> None:
        yaw = sample.calibrated_yaw
        pitch = sample.calibrated_pitch

        target_pan = self._config.neutral_pan + (-yaw * self._config.yaw_gain)
        target_tilt = self._config.neutral_tilt + (-pitch * self._config.pitch_gain)

        target_pan = self._clamp(
            target_pan,
            self._config.neutral_pan - self._config.max_pan_offset,
            self._config.neutral_pan + self._config.max_pan_offset,
        )
        target_tilt = self._clamp(
            target_tilt,
            self._config.neutral_tilt - self._config.max_tilt_offset,
            self._config.neutral_tilt + self._config.max_tilt_offset,
        )

        alpha = self._config.smoothing
        self._pan = self._pan + alpha * (target_pan - self._pan)
        self._tilt = self._tilt + alpha * (target_tilt - self._tilt)

        self._controller.set_angles(self._pan, self._tilt, smooth=False)
