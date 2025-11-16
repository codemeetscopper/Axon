"""Interactive control surface for the desktop simulator."""

from __future__ import annotations

import random
from functools import partial

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtNetwork import QAbstractSocket

from axon_ui import RoboticFaceWidget, TelemetryPanel
from robot_control.remote_bridge import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    RemoteBridgeController,
)


class ControlPanel(QWidget):
    """Right-hand control column for the desktop simulator."""

    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        controller: RemoteBridgeController,
        *,
        default_host: str = DEFAULT_BRIDGE_HOST,
        default_port: int = DEFAULT_BRIDGE_PORT,
        auto_connect: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.face = face
        self.telemetry = telemetry
        self._controller = controller
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(2600)
        self._cycle_timer.timeout.connect(self._advance_cycle)
        self._orientation_values: dict[str, float] = {
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
        }
        self.sliders: dict[str, QSlider] = {}
        self._build_ui(default_host, default_port)
        self._controller.connectionStateChanged.connect(self._handle_state_changed)
        self._controller.lineReceived.connect(self._append_bridge_line)
        self._controller.errorOccurred.connect(self._handle_bridge_error)
        if auto_connect:
            QTimer.singleShot(0, self._connect_to_robot)

    def _build_ui(self, default_host: str, default_port: int) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Emotion")
        title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(title)

        self.emotion_combo = QComboBox()
        self.emotion_combo.addItems(self.face.available_emotions())
        self.emotion_combo.currentTextChanged.connect(self.face.set_emotion)
        layout.addWidget(self.emotion_combo)

        self.cycle_checkbox = QCheckBox("Cycle emotions")
        self.cycle_checkbox.toggled.connect(self._toggle_cycle)
        layout.addWidget(self.cycle_checkbox)

        layout.addSpacing(20)

        orient_title = QLabel("Orientation")
        orient_title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(orient_title)

        grid = QGridLayout()
        grid.setVerticalSpacing(16)
        grid.setHorizontalSpacing(12)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        for row, (axis, rng) in enumerate((("yaw", 45), ("pitch", 30), ("roll", 25))):
            label = QLabel(axis.upper())
            label.setStyleSheet("font-size: 14px; font-weight: 500;")
            grid.addWidget(label, row, 0)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-rng, rng)
            slider.setValue(int(self._orientation_values[axis]))
            slider.setSingleStep(1)
            slider.valueChanged.connect(partial(self._update_orientation, axis))
            grid.addWidget(slider, row, 1)
            self.sliders[axis] = slider

            value_label = QLabel("0°")
            value_label.setObjectName(f"value_{axis}")
            value_label.setFixedWidth(48)
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(value_label, row, 2)

        layout.addSpacing(10)

        reset_btn = QPushButton("Reset Orientation")
        reset_btn.clicked.connect(self._reset_orientation)
        layout.addWidget(reset_btn)

        shuffle_btn = QPushButton("Surprise Me ✨")
        shuffle_btn.clicked.connect(self._random_emotion)
        layout.addWidget(shuffle_btn)

        layout.addSpacing(18)

        conn_title = QLabel("Robot connection")
        conn_title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(conn_title)

        host_layout = QHBoxLayout()
        host_layout.setSpacing(12)
        host_label = QLabel("Host")
        host_label.setFixedWidth(36)
        host_layout.addWidget(host_label)
        self.host_input = QLineEdit(default_host)
        self.host_input.setPlaceholderText(DEFAULT_BRIDGE_HOST)
        host_layout.addWidget(self.host_input, 1)
        layout.addLayout(host_layout)

        port_layout = QHBoxLayout()
        port_layout.setSpacing(12)
        port_label = QLabel("Port")
        port_label.setFixedWidth(36)
        port_layout.addWidget(port_label)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(default_port)
        port_layout.addWidget(self.port_input, 1)
        layout.addLayout(port_layout)

        self.status_label = QLabel("Disconnected")
        self.status_label.setObjectName("connectionStatusLabel")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.7);")
        layout.addWidget(self.status_label)

        self.connect_button = QPushButton("Connect to robot")
        self.connect_button.clicked.connect(self._toggle_connection)
        layout.addWidget(self.connect_button)

        command_title = QLabel("Raw serial command")
        command_title.setStyleSheet("font-size: 14px; font-weight: 500; margin-top: 8px;")
        layout.addWidget(command_title)

        command_layout = QHBoxLayout()
        command_layout.setSpacing(8)
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("e.g. set emotion happy")
        command_layout.addWidget(self.command_input, 1)
        send_button = QPushButton("Send")
        send_button.clicked.connect(self._send_raw_command)
        command_layout.addWidget(send_button)
        layout.addLayout(command_layout)

        self.console = QPlainTextEdit()
        self.console.setPlaceholderText("Bridge output will appear here")
        self.console.setReadOnly(True)
        self.console.setMaximumBlockCount(300)
        layout.addWidget(self.console, 1)

        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def _set_value_label(self, object_name: str, text: str) -> None:
        label = self.findChild(QLabel, object_name)
        if label is not None:
            label.setText(text)

    def _update_orientation(self, axis: str, value: int) -> None:
        self.face.set_orientation(**{axis: float(value)})
        self._orientation_values[axis] = float(value)
        self._set_value_label(f"value_{axis}", f"{value}°")

    def _reset_orientation(self) -> None:
        self.face.set_orientation(yaw=0.0, pitch=0.0, roll=0.0)
        for axis, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            self._orientation_values[axis] = 0.0
            self._set_value_label(f"value_{axis}", "0°")

    def _random_emotion(self) -> None:
        emotions = list(self.face.available_emotions())
        if not emotions:
            return
        current_text = self.emotion_combo.currentText()
        choices = [emotion for emotion in emotions if emotion != current_text]
        next_emotion = random.choice(choices or emotions)
        self.emotion_combo.setCurrentText(next_emotion)

    def _toggle_cycle(self, enabled: bool) -> None:
        if enabled and len(self.face.available_emotions()) > 1:
            self._cycle_timer.start()
        else:
            self._cycle_timer.stop()

    def _advance_cycle(self) -> None:
        emotions = list(self.face.available_emotions())
        if len(emotions) < 2:
            return
        current_text = self.emotion_combo.currentText()
        try:
            index = emotions.index(current_text)
        except ValueError:
            index = -1
        next_emotion = emotions[(index + 1) % len(emotions)]
        if next_emotion != current_text:
            self.emotion_combo.setCurrentText(next_emotion)

    def _toggle_connection(self) -> None:
        if self._controller.is_connected():
            self._controller.disconnect()
            return
        self._connect_to_robot()

    def _connect_to_robot(self) -> None:
        host = self.host_input.text().strip() or DEFAULT_BRIDGE_HOST
        port = int(self.port_input.value())
        self._append_bridge_line(f"Connecting to {host}:{port}...")
        self._controller.connect_to(host, port)

    def _send_raw_command(self) -> None:
        command = self.command_input.text().strip()
        if not command:
            return
        try:
            self._controller.send_command(command)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Serial bridge", str(exc))
            return
        self._append_bridge_line(f">> {command}")
        self.command_input.clear()

    def _append_bridge_line(self, line: str) -> None:
        if not line:
            return
        self.console.appendPlainText(line)

    def _handle_bridge_error(self, message: str) -> None:
        self._append_bridge_line(f"Error: {message}")

    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:
        mapping = {
            QAbstractSocket.SocketState.UnconnectedState: "Disconnected",
            QAbstractSocket.SocketState.HostLookupState: "Resolving host...",
            QAbstractSocket.SocketState.ConnectingState: "Connecting...",
            QAbstractSocket.SocketState.ConnectedState: "Connected",
            QAbstractSocket.SocketState.ClosingState: "Closing",
        }
        self.status_label.setText(mapping.get(state, "Unknown state"))
        if state == QAbstractSocket.SocketState.ConnectedState:
            self.connect_button.setText("Disconnect")
            self.host_input.setEnabled(False)
            self.port_input.setEnabled(False)
        elif state == QAbstractSocket.SocketState.ConnectingState:
            self.connect_button.setText("Cancel")
            self.host_input.setEnabled(False)
            self.port_input.setEnabled(False)
        else:
            self.connect_button.setText("Connect to robot")
            self.host_input.setEnabled(True)
            self.port_input.setEnabled(True)
