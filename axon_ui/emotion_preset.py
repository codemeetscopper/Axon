"""Definition of the face widget's emotion presets."""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class EmotionPreset:
    name: str
    eye_openness: float
    eye_curve: float
    brow_raise: float
    brow_tilt: float
    mouth_curve: float
    mouth_open: float
    mouth_width: float
    mouth_height: float
    iris_size: float
    accent_color: Tuple[int, int, int]
