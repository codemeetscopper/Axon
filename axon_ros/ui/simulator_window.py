"""Desktop window that hosts the robotic face widget and control panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget, QHBoxLayout, QSplitter, QLabel

from axon_ros.ui.bridge_chassis_panel import BridgeChassisPanel
from axon_ros.ui.bridge_command_panel import BridgeCommandPanel
from axon_ros.ui.control_panel import ControlPanel
from axon_ros.ui.robot_link_panel import RobotLinkPanel
from axon_ros.ui.face_telemetry_display import FaceTelemetryDisplay
from axon_ros.ui.viz_config_panel import VizConfigPanel
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from robot_control import EmotionPolicy, GyroCalibrator


from motion.robot_gl_widget import RobotGLWidget

class SimulatorMainWindow(QWidget):
    def __init__(
        self,
        *,
        bridge_host: str | None = None,
        bridge_port: int | None = None,
        policy: EmotionPolicy | None = None,
        calibrator: GyroCalibrator | None = None,
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter to allow resizing between left (viz) and right (controls)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #333; }")
        layout.addWidget(self.splitter)

        # --- LEFT COLUMN (Visualization) ---
        viz_container = QWidget()
        viz_layout = QVBoxLayout(viz_container)
        viz_layout.setContentsMargins(24, 24, 24, 24)
        viz_layout.setSpacing(24)

        self.face = RoboticFaceWidget()
        self.telemetry = TelemetryPanel()
        self.info_panel = InfoPanel()
        self.info_panel.displayModeToggleRequested.connect(self._toggle_window_mode)

        display = FaceTelemetryDisplay(self.face, (self.info_panel, self.telemetry))
        
        # 3D Viewer Container
        gl_container = QWidget()
        gl_container.setObjectName("glContainer")
        gl_container.setStyleSheet("""
            #glContainer {
                background-color: #1e1e1e;
                border: 1px solid #333;
                border-radius: 12px;
            }
            QLabel {
                color: #aaa;
                font-weight: bold;
                padding: 4px;
            }
        """)
        gl_layout = QVBoxLayout(gl_container)
        gl_layout.setContentsMargins(0, 0, 0, 0)
        gl_layout.setSpacing(0)
        
        # Create 3D viewer
        # Load default.stl from the same directory as this file
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        stl_path = os.path.join(current_dir, "default.stl")
        
        self.robot_gl = RobotGLWidget(stl_path=stl_path, scale=0.8)
        self.robot_gl.setMinimumHeight(250)
        # Round corners for the GL widget itself if possible, or just let container handle it
        # OpenGL widgets can be tricky with border-radius, so we rely on the container frame
        
        gl_layout.addWidget(self.robot_gl)
        
        viz_layout.addWidget(display, 3)
        viz_layout.addWidget(gl_container, 2)
        
        self.splitter.addWidget(viz_container)

        # --- RIGHT COLUMN (Controls) ---
        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 24, 24, 24) # Top, Right, Bottom margins
        
        self.control_panel = ControlPanel(self.face, self.telemetry)
        self.control_panel.setObjectName("controlPanel")
        self.control_panel.setMinimumWidth(320)

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
        
        # Connect telemetry to 3D viewer
        self.robot_link_panel.controller.telemetryReceived.connect(self.robot_gl.set_orientation_from_sample)
        
        controller = self.robot_link_panel.controller
        self.bridge_chassis_panel = BridgeChassisPanel(controller, self)
        self.bridge_command_panel = BridgeCommandPanel(controller, self)
        
        # Visualization Config Panel
        self.viz_config = VizConfigPanel()
        self.viz_config.configChanged.connect(self.robot_gl.set_mesh_transform)

        tabs = QTabWidget()
        tabs.addTab(self.control_panel, "Simulator")
        tabs.addTab(self.robot_link_panel, "Robot link")
        tabs.addTab(self.bridge_chassis_panel, "Chassis control")
        tabs.addTab(self.bridge_command_panel, "Robot commands")
        tabs.addTab(self.viz_config, "Viz Config")
        
        controls_layout.addWidget(tabs)
        self.splitter.addWidget(controls_container)
        
        # Set initial splitter sizes (give more space to viz)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

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
