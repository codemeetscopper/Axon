"""Top-level Qt window for the Axon runtime and remote UI."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtWidgets import QVBoxLayout, QWidget

from axon_ros.ui.face_telemetry_display import FaceTelemetryDisplay
from axon_ui import InfoPanel, RoboticFaceWidget


class RobotMainWindow(QWidget):
    """Embed the face widget with the telemetry overlays in a fullscreen shell."""

    def __init__(
        self,
        face_widget: RoboticFaceWidget,
        overlays: Sequence[QWidget] | QWidget,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Axon Runtime")
        self._display = FaceTelemetryDisplay(
            face_widget,
            overlays,
            parent=self,
            fixed_size=None,
        )
        self._register_info_controls(overlays)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._display)

    def _register_info_controls(self, overlays: Sequence[QWidget] | QWidget) -> None:
        widgets: Sequence[QWidget]
        if isinstance(overlays, Sequence):
            widgets = overlays
        else:
            widgets = (overlays,)
        for widget in widgets:
            if isinstance(widget, InfoPanel):
                widget.displayModeToggleRequested.connect(self._toggle_window_mode)

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
