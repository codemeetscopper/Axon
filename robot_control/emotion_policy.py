from __future__ import annotations

from dataclasses import dataclass

from .sensor_data import SensorSample


@dataclass(slots=True)
class EmotionPolicy:
    """Select an emotion based on gyroscope readings."""

    default_emotion: str = "happy"
    alert_emotion: str = "surprised"
    tilt_emotion: str = "sad"
    roll_alert_threshold: float = 25.0
    roll_sad_threshold: float = 8.0
    pitch_threshold: float = 20.0
    yaw_threshold: float = 15.0

    def choose(self, sample: SensorSample, current: str | None = None) -> str:
        """Return the emotion that should be shown for the given sample."""

        roll = abs(sample.calibrated_roll)
        pitch = abs(sample.calibrated_pitch)
        yaw = abs(sample.calibrated_yaw)

        if pitch > self.pitch_threshold or roll > self.roll_alert_threshold:
            return self.alert_emotion
        if roll > self.roll_sad_threshold or yaw > self.yaw_threshold:
            return self.tilt_emotion
        if current in {self.alert_emotion, self.tilt_emotion}:
            return self.default_emotion
        return current or self.default_emotion
