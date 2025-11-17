from __future__ import annotations

from collections import deque
from statistics import mean
from time import monotonic
from typing import Deque, Tuple

from .sensor_data import SensorSample, set_calibration_offsets


class GyroCalibrator:
    """Automatically learn gyro baselines when the robot is stationary."""

    def __init__(
        self,
        window_seconds: float = 3.0,
        roll_threshold: float = 1.0,
        pitch_threshold: float = 1.0,
        yaw_threshold: float = 2.0,
    ) -> None:
        self._window = window_seconds
        self._roll_threshold = roll_threshold
        self._pitch_threshold = pitch_threshold
        self._yaw_threshold = yaw_threshold
        self._samples: Deque[Tuple[float, float, float, float]] = deque()
        self._current_offsets: Tuple[float, float, float] | None = None

    def observe(self, sample: SensorSample, timestamp: float | None = None) -> bool:
        """Record *sample* and update the baseline when it rests for the window.

        Returns ``True`` when a new set of offsets is applied.
        """

        if timestamp is None:
            timestamp = monotonic()

        self._samples.append((timestamp, sample.roll, sample.pitch, sample.yaw))
        self._prune(timestamp)

        if not self._has_full_window(timestamp):
            return False

        if not self._is_stable():
            return False

        offsets = self._window_average()
        if self._current_offsets and self._offsets_close(offsets, self._current_offsets):
            return False

        self._current_offsets = offsets
        roll, pitch, yaw = offsets
        set_calibration_offsets(roll=roll, pitch=pitch, yaw=yaw)
        return True

    def reset(self, *, forget_offsets: bool = False) -> None:
        """Clear the sliding window so a fresh baseline can be captured."""

        self._samples.clear()
        if forget_offsets:
            self._current_offsets = None

    @property
    def current_offsets(self) -> Tuple[float, float, float] | None:
        return self._current_offsets

    def seconds_to_window_completion(self, now: float | None = None) -> float | None:
        """Return the estimated number of seconds left before the window is full."""

        if not self._samples:
            return self._window
        if now is None:
            now = monotonic()
        oldest = self._samples[0][0]
        remaining = self._window - max(0.0, now - oldest)
        return max(0.0, remaining)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _prune(self, now: float) -> None:
        while self._samples and (now - self._samples[0][0]) > self._window:
            self._samples.popleft()

    def _has_full_window(self, now: float) -> bool:
        if not self._samples:
            return False
        return (now - self._samples[0][0]) >= self._window * 0.95

    def _is_stable(self) -> bool:
        rolls = [sample[1] for sample in self._samples]
        pitches = [sample[2] for sample in self._samples]
        yaws = [sample[3] for sample in self._samples]

        return (
            (max(rolls) - min(rolls) <= self._roll_threshold)
            and (max(pitches) - min(pitches) <= self._pitch_threshold)
            and (max(yaws) - min(yaws) <= self._yaw_threshold)
        )

    def _window_average(self) -> Tuple[float, float, float]:
        rolls = [sample[1] for sample in self._samples]
        pitches = [sample[2] for sample in self._samples]
        yaws = [sample[3] for sample in self._samples]
        return (mean(rolls), mean(pitches), mean(yaws))

    def _offsets_close(
        self,
        new_offsets: Tuple[float, float, float],
        current_offsets: Tuple[float, float, float],
        tolerance: float = 0.2,
    ) -> bool:
        return all(abs(a - b) <= tolerance for a, b in zip(new_offsets, current_offsets))
