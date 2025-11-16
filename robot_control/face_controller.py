from __future__ import annotations

from time import monotonic
from typing import Optional

from PySide6.QtCore import QObject

from axon_ui import RoboticFaceWidget

from .emotion_policy import EmotionPolicy
from .sensor_data import SensorSample


class FaceController(QObject):
    """Bridge between telemetry samples and the :class:`RoboticFaceWidget`."""

    def __init__(
        self,
        face: RoboticFaceWidget,
        policy: Optional[EmotionPolicy] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._face = face
        self._policy = policy or EmotionPolicy()
        self._current_emotion: str | None = None
        self._rest_start: float | None = None
        self._last_cycle_time: float = 0.0
        self._rest_delay = 3.0
        self._rest_interval = 3.0
        self._rest_sequence: tuple[str, ...] = self._build_rest_sequence()
        self._previous_sample: SensorSample | None = None

    def apply_sample(self, sample: SensorSample) -> None:
        """Update the face to reflect the latest telemetry sample."""

        self._face.set_orientation(**sample.to_orientation())

        now = monotonic()
        previous = self._previous_sample
        resting = sample.is_resting(previous_sample=previous)
        next_emotion: Optional[str]

        cycle_emotion: Optional[str] = None
        if resting:
            if self._rest_start is None:
                self._rest_start = now
                self._last_cycle_time = now
            if (now - self._rest_start) >= self._rest_delay and (now - self._last_cycle_time) >= self._rest_interval:
                cycle_emotion = self._next_rest_emotion()
                self._last_cycle_time = now
        else:
            self._rest_start = None
            self._last_cycle_time = 0.0

        if cycle_emotion:
            next_emotion = cycle_emotion
        elif not resting:
            next_emotion = self._policy.choose(sample, current=self._current_emotion)
            if (
                next_emotion == self._current_emotion
                and self._current_emotion not in (
                    None,
                    self._policy.default_emotion,
                    self._policy.alert_emotion,
                    self._policy.tilt_emotion,
                )
            ):
                next_emotion = self._policy.default_emotion
        else:
            if self._current_emotion in (self._policy.alert_emotion, self._policy.tilt_emotion):
                next_emotion = self._policy.default_emotion
            else:
                next_emotion = self._current_emotion or self._policy.default_emotion

        self._previous_sample = sample

        if not next_emotion or next_emotion == self._current_emotion:
            return

        available = list(self._face.available_emotions())
        if next_emotion not in available:
            fallback = self._policy.default_emotion
            next_emotion = fallback if fallback in available else (available[0] if available else None)
        if next_emotion:
            self._face.set_emotion(next_emotion)
            self._current_emotion = next_emotion

    @property
    def current_emotion(self) -> Optional[str]:
        return self._current_emotion

    def _build_rest_sequence(self) -> tuple[str, ...]:
        excluded = {self._policy.alert_emotion, self._policy.tilt_emotion}
        available = [emotion for emotion in self._face.available_emotions() if emotion not in excluded]
        if not available:
            return tuple()

        if self._policy.default_emotion in available:
            start = available.index(self._policy.default_emotion)
            ordered = available[start:] + available[:start]
        else:
            ordered = available
        return tuple(ordered)

    def _next_rest_emotion(self) -> Optional[str]:
        if not self._rest_sequence:
            return None

        if self._current_emotion in self._rest_sequence:
            current_index = self._rest_sequence.index(self._current_emotion)
            next_index = (current_index + 1) % len(self._rest_sequence)
        else:
            next_index = 0

        return self._rest_sequence[next_index]
