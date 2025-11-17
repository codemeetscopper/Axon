"""Desktop window that hosts the robotic face widget and control panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget, QHBoxLayout

from axon_ros.ui.control_panel import ControlPanel
from axon_ros.ui.robot_link_panel import RobotLinkPanel
from axon_ros.ui.face_telemetry_display import FaceTelemetryDisplay
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from robot_control import EmotionPolicy, GyroCalibrator


class SimulatorMainWindow(QWidget):
    def __init__(
        self,
        *,
        bridge_host: str | None = None,
        bridge_port: int | None = None,
        policy: "EmotionPolicy" | None = None,
        calibrator: "GyroCalibrator" | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Robotic Face Widget")
        self._bridge_host = bridge_host
        self._bridge_port = bridge_port
        self._policy = policy
        self._calibrator = calibrator
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.face = RoboticFaceWidget()
        self.telemetry = TelemetryPanel()
        self.info_panel = InfoPanel()
        self.info_panel.displayModeToggleRequested.connect(self._toggle_window_mode)

        display = FaceTelemetryDisplay(self.face, (self.info_panel, self.telemetry))
        layout.addWidget(display, 1)

        self.control_panel = ControlPanel(self.face, self.telemetry)
        self.control_panel.setObjectName("controlPanel")
        self.control_panel.setMinimumWidth(280)

        self.robot_link_panel = RobotLinkPanel(
            self.face,
            self.telemetry,
            default_host=self._bridge_host,
            default_port=self._bridge_port,
            policy=self._policy,
            calibrator=self._calibrator,
        )
        self.robot_link_panel.remoteControlChanged.connect(self._handle_remote_toggle)
        self.robot_link_panel.linkStateChanged.connect(self._handle_remote_link_state)

        tabs = QTabWidget()
        tabs.addTab(self.control_panel, "Simulator")
        tabs.addTab(self.robot_link_panel, "Robot link")
        layout.addWidget(tabs, 0, Qt.AlignmentFlag.AlignBottom)

        self.face.set_emotion("happy")

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _handle_remote_toggle(self, active: bool) -> None:
        self.control_panel.set_simulation_enabled(not active)

    def _handle_remote_link_state(self, active: bool, host: str, port: int) -> None:
        if active:
            self.info_panel.set_manual_entries(ip=f"Robot: {host}:{port}", wifi="Serial bridge")
        else:
            self.info_panel.set_manual_entries(ip=None, wifi=None)
            self.control_panel.apply_simulation_state()

    def shutdown(self) -> None:
        self.robot_link_panel.shutdown()
