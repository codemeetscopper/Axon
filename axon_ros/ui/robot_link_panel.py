"""Robot connection tab for the simulator control column."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from axon_ui import RoboticFaceWidget, TelemetryPanel
from robot_control.emotion_policy import EmotionPolicy
from robot_control.gyro_calibrator import GyroCalibrator
from robot_control.sensor_data import SensorSample, get_calibration_offsets
from robot_control.remote_bridge import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    RemoteBridgeController,
)


class RobotLinkPanel(QWidget):
    """Allow the simulator to talk to the robot over the serial bridge."""

    remoteControlChanged = Signal(bool)
    linkStateChanged = Signal(bool, str, int)

    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        *,
        default_host: str | None = None,
        default_port: int | None = None,
        policy: EmotionPolicy | None = None,
        calibrator: GyroCalibrator | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = RemoteBridgeController(face, telemetry, policy=policy, parent=self)
        self._controller.connectionStateChanged.connect(self._handle_state_changed)
        self._controller.remoteActiveChanged.connect(self._handle_remote_active)
        self._controller.lineReceived.connect(self._append_bridge_line)
        self._controller.errorOccurred.connect(self._handle_error)
        self._controller.telemetryReceived.connect(self._handle_telemetry)
        self._last_host = default_host or DEFAULT_BRIDGE_HOST
        self._last_port = default_port or DEFAULT_BRIDGE_PORT
        self._calibrator = calibrator
        self._calibration_active = False
        self._calibration_status: QLabel | None = None
        self._calibration_button: QPushButton | None = None
        self._calibration_labels: dict[str, QLabel] = {}

        self._host_edit = QLineEdit(self)
        self._port_spin = QSpinBox(self)
        self._status_label = QLabel("Disconnected", self)
        self._connect_button = QPushButton("Connect", self)
        self._log_view = QPlainTextEdit(self)
        self._command_input = QLineEdit(self)
        self._send_button = QPushButton("Send", self)

        self._host_edit.setPlaceholderText(DEFAULT_BRIDGE_HOST)
        self._host_edit.setText(default_host or DEFAULT_BRIDGE_HOST)
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(default_port or DEFAULT_BRIDGE_PORT)
        self._port_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._status_label.setObjectName("robotLinkStatus")
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(500)
        self._log_view.setPlaceholderText("Bridge log will appear here")
        self._log_view.setObjectName("robotLinkLog")
        self._command_input.setPlaceholderText("Enter raw serial command")
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self._connect_button.clicked.connect(self._toggle_connection)
        self._send_button.clicked.connect(self._send_command)
        self._command_input.returnPressed.connect(self._send_command)

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(8)
        layout.addLayout(form)

        form.addWidget(QLabel("Bridge host"), 0, 0)
        form.addWidget(self._host_edit, 0, 1)

        form.addWidget(QLabel("Bridge port"), 1, 0)
        form.addWidget(self._port_spin, 1, 1)

        form.addWidget(QLabel("Status"), 2, 0)
        form.addWidget(self._status_label, 2, 1)

        self._connect_button.setObjectName("robotLinkConnect")
        form.addWidget(self._connect_button, 3, 0, 1, 2)

        layout.addWidget(QLabel("Serial log"))
        layout.addWidget(self._log_view, 1)

        command_row = QHBoxLayout()
        command_row.setSpacing(8)
        command_row.addWidget(self._command_input, 1)
        command_row.addWidget(self._send_button, 0)
        layout.addLayout(command_row)

        if self._calibrator is not None:
            layout.addSpacing(12)
            layout.addWidget(self._build_calibrator_panel())
        layout.addStretch(1)

    def _apply_styles(self) -> None:
        self._status_label.setStyleSheet("font-weight: 600;")
        self._log_view.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.04);"
            "border: 1px solid rgba(255, 255, 255, 0.08);"
            "border-radius: 8px;"
            "font-family: 'JetBrains Mono', 'Fira Code', monospace;"
            "font-size: 12px;"
        )
        self._connect_button.setStyleSheet(
            "#robotLinkConnect {"
            "background-color: #4361EE;"
            "border: none;"
            "border-radius: 6px;"
            "color: white;"
            "padding: 6px 12px;"
            "font-weight: 600;"
            "}"
        )

    def _toggle_connection(self) -> None:
        state = self._controller.state()
        if state in (
            QAbstractSocket.SocketState.ConnectingState,
            QAbstractSocket.SocketState.ConnectedState,
        ):
            self._append_message("Disconnecting from bridge")
            self._controller.disconnect()
            return

        host = self._host_edit.text().strip() or DEFAULT_BRIDGE_HOST
        port = int(self._port_spin.value())
        self._last_host = host
        self._last_port = port
        self._append_message(f"Connecting to {host}:{port}")
        self._controller.connect_to(host, port)

    def _send_command(self) -> None:
        payload = self._command_input.text().strip()
        if not payload:
            return
        try:
            self._controller.send_command(payload)
        except RuntimeError as exc:
            self._append_message(f"Command failed: {exc}")
            return
        self._append_message(f">> {payload}")
        self._command_input.clear()

    def _append_bridge_line(self, line: str) -> None:
        self._append_message(line)

    def _handle_error(self, message: str) -> None:
        self._append_message(f"Error: {message}")

    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:
        label = {
            QAbstractSocket.SocketState.UnconnectedState: "Disconnected",
            QAbstractSocket.SocketState.HostLookupState: "Looking up host",
            QAbstractSocket.SocketState.ConnectingState: "Connecting",
            QAbstractSocket.SocketState.ConnectedState: "Connected",
            QAbstractSocket.SocketState.ClosingState: "Closing",
        }.get(state, "Unknown")
        self._status_label.setText(label)
        if state == QAbstractSocket.SocketState.ConnectedState:
            self._connect_button.setText("Disconnect")
        else:
            self._connect_button.setText("Connect")

    def _handle_remote_active(self, active: bool) -> None:
        self.remoteControlChanged.emit(active)
        if active:
            self._append_message("Bridge connected")
            if self._calibration_status is not None and not self._calibration_active:
                self._calibration_status.setText("Link ready")
        else:
            self._append_message("Bridge inactive")
            self._calibration_active = False
            if self._calibration_status is not None:
                self._calibration_status.setText("Robot link inactive")
        if self._calibration_button is not None:
            self._calibration_button.setEnabled(active and not self._calibration_active)
        self._emit_link_state(active)

    def _emit_link_state(self, active: bool) -> None:
        self.linkStateChanged.emit(active, self._last_host, self._last_port)

    def _append_message(self, text: str) -> None:
        self._log_view.appendPlainText(text)
        self._log_view.verticalScrollBar().setValue(
            self._log_view.verticalScrollBar().maximum()
        )

    # ------------------------------------------------------------------
    # Gyro calibration helpers
    # ------------------------------------------------------------------
    def _build_calibrator_panel(self) -> QWidget:
        container = QWidget(self)
        column = QVBoxLayout(container)
        column.setSpacing(6)
        title = QLabel("Gyro calibration")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        column.addWidget(title)

        subtitle = QLabel("Capture fresh roll/pitch/yaw baselines while the robot is resting.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        column.addWidget(subtitle)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_label = QLabel("Status:")
        self._calibration_status = QLabel("Idle")
        status_row.addWidget(status_label)
        status_row.addWidget(self._calibration_status, 1)
        column.addLayout(status_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._calibration_button = QPushButton("Calibrate now", self)
        self._calibration_button.clicked.connect(self._start_calibration)
        self._calibration_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calibration_button.setEnabled(False)
        action_row.addWidget(self._calibration_button)
        column.addLayout(action_row)

        offsets_title = QLabel("Current offsets")
        offsets_title.setStyleSheet("font-size: 14px; font-weight: 500;")
        column.addWidget(offsets_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row, axis in enumerate(("roll", "pitch", "yaw")):
            label = QLabel(axis.title())
            grid.addWidget(label, row, 0)
            value = QLabel("—")
            value.setObjectName(f"calibration_value_{axis}")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value, row, 1)
            self._calibration_labels[axis] = value
        column.addLayout(grid)

        self._update_offset_labels()
        return container

    def _start_calibration(self) -> None:
        if self._calibrator is None:
            return
        if not self._controller.is_connected():
            self._append_message("Cannot calibrate without an active link")
            return
        self._calibrator.reset()
        self._calibration_active = True
        if self._calibration_status is not None:
            self._calibration_status.setText("Collecting samples… hold steady")
        if self._calibration_button is not None:
            self._calibration_button.setEnabled(False)
        self._append_message("Calibration requested — keep the robot motionless")

    def _handle_telemetry(self, sample: SensorSample) -> None:
        if self._calibrator is None:
            return
        updated = self._calibrator.observe(sample)
        if updated:
            offsets = self._calibrator.current_offsets
            if offsets is not None:
                roll, pitch, yaw = offsets
                self._append_message(
                    f"Offsets updated (roll={roll:.2f}, pitch={pitch:.2f}, yaw={yaw:.2f})"
                )
            self._calibration_active = False
            if self._calibration_status is not None:
                self._calibration_status.setText("Offsets applied")
            if self._calibration_button is not None and self._controller.is_connected():
                self._calibration_button.setEnabled(True)
            self._update_offset_labels()
            return

        if self._calibration_active and self._calibration_status is not None:
            remaining = self._calibrator.seconds_to_window_completion()
            if remaining is None:
                self._calibration_status.setText("Waiting for stable readings…")
            elif remaining <= 0:
                self._calibration_status.setText("Stability detected… applying")
            else:
                self._calibration_status.setText(
                    f"Collecting samples ({remaining:.1f}s remaining)"
                )

    def _update_offset_labels(self) -> None:
        offsets = get_calibration_offsets()
        for axis, label in self._calibration_labels.items():
            value = offsets.get(axis)
            label.setText(f"{value:.2f}°" if value is not None else "—")

    def shutdown(self) -> None:
        self._controller.disconnect()
