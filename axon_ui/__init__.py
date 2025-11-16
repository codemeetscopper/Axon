"""Shared UI components for Axon demos and runtime."""

from .face_widget import RoboticFaceWidget
from .info_panel import InfoPanel
from .palette import apply_dark_palette
from .telemetry_panel import TelemetryPanel

__all__ = [
    "RoboticFaceWidget",
    "InfoPanel",
    "TelemetryPanel",
    "apply_dark_palette",
]
