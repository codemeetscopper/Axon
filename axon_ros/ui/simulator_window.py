"""Desktop window that hosts the robotic face widget and control panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from axon_ros.ui.control_panel import ControlPanel
from axon_ros.ui.face_telemetry_display import FaceTelemetryDisplay
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel


class SimulatorMainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Robotic Face Widget")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        self.face = RoboticFaceWidget()
        self.telemetry = TelemetryPanel()
        self.info_panel = InfoPanel()
        self.info_panel.displayModeToggleRequested.connect(self._toggle_window_mode)

        display = FaceTelemetryDisplay(self.face, (self.info_panel, self.telemetry))
        layout.addWidget(display, 0, Qt.AlignmentFlag.AlignTop)

        panel = ControlPanel(self.face, self.telemetry)
        panel.setFixedWidth(280)
        panel.setObjectName("controlPanel")
        layout.addWidget(panel, 1)

        self.face.set_emotion("happy")

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
