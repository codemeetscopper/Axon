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
        self._current_emotion: str | None = self._policy.default_emotion
        self._steady_start: float | None = None
        self._rest_delay = 30.0
        self._sleep_emotion = "sleepy"
        self._sleeping = False
        self._previous_sample: SensorSample | None = None
        self._initialize_face()

    def _initialize_face(self) -> None:
        available = tuple(self._face.available_emotions())
        if self._current_emotion and self._current_emotion in available:
            self._face.set_emotion(self._current_emotion)
        elif available:
            choice = available[0]
            self._face.set_emotion(choice)
            self._current_emotion = choice

    def apply_sample(self, sample: SensorSample) -> None:
        """Update the face to reflect the latest telemetry sample."""

        self._face.set_orientation(**sample.to_orientation())

        now = monotonic()
        previous = self._previous_sample
        major_movement = sample.has_major_movement(previous)
        steady = sample.is_steady(previous)
        next_emotion: Optional[str] = None

        if self._sleeping:
            if major_movement:
                self._sleeping = False
                self._steady_start = None
                next_emotion = self._policy.default_emotion
            else:
                next_emotion = self._sleep_emotion
        else:
            if major_movement:
                self._steady_start = None
            elif steady:
                if self._steady_start is None:
                    self._steady_start = now
                if (now - self._steady_start) >= self._rest_delay:
                    self._sleeping = True
                    next_emotion = self._sleep_emotion
            else:
                self._steady_start = None

        if next_emotion is None:
            if self._sleeping:
                next_emotion = self._sleep_emotion
            else:
                next_emotion = self._policy.choose(
                    sample,
                    current=self._current_emotion,
                    previous=previous,
                )
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

