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
        self._rest_delay = 5.0
        self._sleep_emotion = "sleepy"
        self._sleeping = False
        self._previous_sample: SensorSample | None = None

    def apply_sample(self, sample: SensorSample) -> None:
        """Update the face to reflect the latest telemetry sample."""

        self._face.set_orientation(**sample.to_orientation())

        now = monotonic()
        previous = self._previous_sample
        resting = sample.is_resting(previous_sample=previous)
        next_emotion: Optional[str]

        if resting:
            if self._rest_start is None:
                self._rest_start = now
            if self._sleeping:
                next_emotion = self._sleep_emotion
            elif (now - self._rest_start) >= self._rest_delay:
                next_emotion = self._sleep_emotion
                self._sleeping = True
        else:
            self._rest_start = None
            if self._sleeping:
                if previous is None or sample.has_major_movement(previous):
                    self._sleeping = False
                    next_emotion = self._policy.default_emotion
                else:
                    next_emotion = self._sleep_emotion

        if next_emotion is None and not resting and not self._sleeping:
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
        elif next_emotion is None:
            if self._sleeping:
                next_emotion = self._sleep_emotion
            elif self._current_emotion in (self._policy.alert_emotion, self._policy.tilt_emotion):
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

