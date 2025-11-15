from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject

from robotic_face_widget import RoboticFaceWidget

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

    def apply_sample(self, sample: SensorSample) -> None:
        """Update the face to reflect the latest telemetry sample."""

        self._face.set_orientation(**sample.to_orientation())

        next_emotion = self._policy.choose(sample, current=self._current_emotion)
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
