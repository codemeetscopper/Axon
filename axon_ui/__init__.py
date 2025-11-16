"""Shared UI components for Axon demos and runtime."""

from .face_widget import RoboticFaceWidget
from .palette import apply_dark_palette
from .telemetry import InfoPanel, TelemetryPanel

__all__ = [
    "RoboticFaceWidget",
    "apply_dark_palette",
    "InfoPanel",
    "TelemetryPanel",
]
