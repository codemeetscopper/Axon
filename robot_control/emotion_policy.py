from __future__ import annotations

from dataclasses import dataclass

from .sensor_data import SensorSample


@dataclass(slots=True)
class EmotionPolicy:
    """Select an emotion based on gyroscope readings."""

    default_emotion: str = "happy"
    alert_emotion: str = "fearful"
    tilt_emotion: str = "curious"
    roll_threshold: float = 25.0
    pitch_threshold: float = 20.0
    yaw_threshold: float = 35.0

    def choose(self, sample: SensorSample, current: str | None = None) -> str:
        """Return the emotion that should be shown for the given sample."""

        if (
            abs(sample.calibrated_pitch) > self.pitch_threshold
            or abs(sample.calibrated_roll) > self.roll_threshold
        ):
            return self.alert_emotion
        if abs(sample.calibrated_yaw) > self.yaw_threshold:
            return self.tilt_emotion
        if current in {self.alert_emotion, self.tilt_emotion}:
            return self.default_emotion
        return current or self.default_emotion
