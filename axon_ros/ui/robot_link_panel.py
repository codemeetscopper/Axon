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
from robot_control.remote_bridge import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    RemoteBridgeController,
)


class RobotLinkPanel(QWidget):
    """Allow the simulator to talk to the robot over the serial bridge."""

    remoteControlChanged = Signal(bool)

    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        *,
        default_host: str | None = None,
        default_port: int | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = RemoteBridgeController(face, telemetry, parent=self)
        self._controller.connectionStateChanged.connect(self._handle_state_changed)
        self._controller.remoteActiveChanged.connect(self._handle_remote_active)
        self._controller.lineReceived.connect(self._append_bridge_line)
        self._controller.errorOccurred.connect(self._handle_error)

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
        else:
            self._append_message("Bridge inactive")

    def _append_message(self, text: str) -> None:
        self._log_view.appendPlainText(text)
        self._log_view.verticalScrollBar().setValue(
            self._log_view.verticalScrollBar().maximum()
        )

    def shutdown(self) -> None:
        self._controller.disconnect()
