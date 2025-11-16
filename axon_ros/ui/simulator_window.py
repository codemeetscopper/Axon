"""Desktop window that hosts the robotic face widget and control panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget

from axon_ros.ui.control_panel import ControlPanel
from axon_ros.ui.face_telemetry_display import FaceTelemetryDisplay
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel
from robot_control.remote_bridge import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    RemoteBridgeController,
)


class SimulatorMainWindow(QWidget):
    def __init__(
        self,
        *,
        default_host: str = DEFAULT_BRIDGE_HOST,
        default_port: int = DEFAULT_BRIDGE_PORT,
        auto_connect: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Robotic Face Widget")
        self._build_ui(default_host, default_port, auto_connect)

    def _build_ui(
        self,
        default_host: str,
        default_port: int,
        auto_connect: bool,
    ) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        self.face = RoboticFaceWidget()
        self.telemetry = TelemetryPanel()
        self.info_panel = InfoPanel()
        self.info_panel.displayModeToggleRequested.connect(self._toggle_window_mode)

        display = FaceTelemetryDisplay(self.face, (self.info_panel, self.telemetry))
        layout.addWidget(display, 0, Qt.AlignmentFlag.AlignTop)

        self.bridge_controller = RemoteBridgeController(self.face, self.telemetry, parent=self)
        panel = ControlPanel(
            self.face,
            self.telemetry,
            self.bridge_controller,
            default_host=default_host,
            default_port=default_port,
            auto_connect=auto_connect,
        )
        panel.setFixedWidth(280)
        panel.setObjectName("controlPanel")
        layout.addWidget(panel, 1)

        self.info_panel.set_manual_entries(
            ip=f"Robot: {default_host}:{default_port}", wifi="Serial bridge"
        )
        self.face.set_emotion("happy")

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
