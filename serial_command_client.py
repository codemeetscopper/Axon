#!/usr/bin/env python3
"""Graphical client for the Axon serial TCP bridge."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from axon_ui.bridge_client import SerialBridgeConnection

DEFAULT_PORT = 8765


@dataclass(frozen=True)
class TelemetryField:
    key: str
    label: str
    formatter: str


TELEMETRY_FIELDS: tuple[TelemetryField, ...] = (
    TelemetryField("left_speed", "Left Speed", "{:.0f}"),
    TelemetryField("right_speed", "Right Speed", "{:.0f}"),
    TelemetryField("roll", "Roll", "{:+.1f}°"),
    TelemetryField("pitch", "Pitch", "{:+.1f}°"),
    TelemetryField("yaw", "Yaw", "{:+.1f}°"),
    TelemetryField("temperature_c", "Temp", "{:.1f}°C"),
    TelemetryField("voltage_v", "Voltage", "{:.2f}V"),
)


class TelemetryBoard(QFrame):
    """Compact grid showing the latest telemetry snapshot."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("telemetryBoard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(
            "#telemetryBoard {"
            "  background-color: rgba(6, 12, 26, 0.85);"
            "  border: 1px solid rgba(255, 255, 255, 0.08);"
            "  border-radius: 12px;"
            "}"
            "#telemetryBoard QLabel {"
            "  color: #e2ecff;"
            "}"
            "#telemetryBoard QLabel.value {"
            "  font-size: 18px;"
            "  font-weight: 600;"
            "}"
            "#telemetryBoard QLabel.label {"
            "  font-size: 12px;"
            "  text-transform: uppercase;"
            "  letter-spacing: 2px;"
            "  color: rgba(226, 236, 255, 0.65);"
            "}"
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setHorizontalSpacing(24)
        layout.setVerticalSpacing(8)
        self._value_labels: dict[str, QLabel] = {}

        for index, field in enumerate(TELEMETRY_FIELDS):
            row = index // 3
            column = index % 3
            name_label = QLabel(field.label)
            name_label.setObjectName("telemetryLabel")
            name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            name_label.setProperty("class", "label")
            value_label = QLabel("--")
            value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value_label.setProperty("class", "value")
            layout.addWidget(name_label, row * 2, column)
            layout.addWidget(value_label, row * 2 + 1, column)
            self._value_labels[field.key] = value_label

    def update_values(self, payload: dict[str, object]) -> None:
        for field in TELEMETRY_FIELDS:
            raw_value = payload.get(field.key)
            label = self._value_labels[field.key]
            if raw_value is None:
                label.setText("--")
                continue
            try:
                label.setText(field.formatter.format(float(raw_value)))
            except (TypeError, ValueError):
                label.setText(str(raw_value))


class SerialBridgeClient(QMainWindow):
    def __init__(self, *, host: str, port: int) -> None:
        super().__init__()
        self.setWindowTitle("Axon Serial Bridge Client")
        self._connection = SerialBridgeConnection(self)
        self._connection.telemetryReceived.connect(self._handle_telemetry)
        self._connection.lineReceived.connect(self._handle_line)
        self._connection.stateChanged.connect(self._handle_state_changed)
        self._connection.errorOccurred.connect(self._handle_error)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        connection_bar = QHBoxLayout()
        connection_bar.setSpacing(8)
        self._host_input = QLineEdit(host)
        self._host_input.setPlaceholderText("Robot IP address")
        self._host_input.setClearButtonEnabled(True)
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(port)
        self._connect_button = QPushButton("Connect")
        self._connect_button.clicked.connect(self._toggle_connection)
        self._status_label = QLabel("Disconnected")
        status_font = QFont()
        status_font.setBold(True)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("color: #f94144;")

        connection_bar.addWidget(QLabel("Host:"))
        connection_bar.addWidget(self._host_input, 2)
        connection_bar.addWidget(QLabel("Port:"))
        connection_bar.addWidget(self._port_input)
        connection_bar.addWidget(self._connect_button)
        connection_bar.addWidget(self._status_label)
        connection_bar.addStretch(1)
        layout.addLayout(connection_bar)

        self._telemetry = TelemetryBoard()
        layout.addWidget(self._telemetry)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #0c111f;"
            "  color: #e8f1ff;"
            "  border-radius: 12px;"
            "  padding: 8px;"
            "  border: 1px solid rgba(255, 255, 255, 0.08);"
            "}"
        )
        layout.addWidget(self._log, 1)

        command_bar = QHBoxLayout()
        command_bar.setSpacing(8)
        self._command_input = QLineEdit()
        self._command_input.setPlaceholderText("Enter command and press Enter")
        self._command_input.returnPressed.connect(self._send_command)
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._send_command)
        self._clear_button = QPushButton("Clear Log")
        self._clear_button.clicked.connect(self._log.clear)
        command_bar.addWidget(self._command_input, 3)
        command_bar.addWidget(self._send_button)
        command_bar.addWidget(self._clear_button)
        layout.addLayout(command_bar)

        self.resize(900, 640)
        self._update_ui_state()

    # ------------------------------------------------------------------
    # Socket handlers
    # ------------------------------------------------------------------
    def _toggle_connection(self) -> None:
        state = self._connection.state()
        if state in (
            QAbstractSocket.SocketState.ConnectingState,
            QAbstractSocket.SocketState.ConnectedState,
        ):
            self._connection.disconnect()
            return
        host = self._host_input.text().strip() or "127.0.0.1"
        port = int(self._port_input.value())
        self._append_log(f"Connecting to {host}:{port}...")
        self._connection.connect_to(host, port)
        self._update_ui_state()

    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:
        if state == QAbstractSocket.SocketState.ConnectedState:
            self._append_log("Connected to bridge.")
        elif state == QAbstractSocket.SocketState.UnconnectedState:
            self._append_log("Disconnected from bridge.")
        self._update_ui_state()

    def _handle_error(self, message: str) -> None:  # pragma: no cover - Qt callback
        self._append_log(f"Socket error: {message}")
        self._update_ui_state()

    def _handle_telemetry(self, data: dict[str, object]) -> None:
        self._telemetry.update_values(data)
        raw = data.get("raw")
        if raw is not None:
            self._append_log(str(raw))

    def _handle_line(self, line: str) -> None:
        if line:
            self._append_log(line)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _update_ui_state(self) -> None:
        connected = self._connection.is_connected()
        connecting = self._connection.is_connecting()
        if connected:
            self._connect_button.setText("Disconnect")
            self._status_label.setText("Connected")
            self._status_label.setStyleSheet("color: #2dd881;")
        elif connecting:
            self._connect_button.setText("Cancel")
            self._status_label.setText("Connecting...")
            self._status_label.setStyleSheet("color: #ffd166;")
        else:
            self._connect_button.setText("Connect")
            self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet("color: #f94144;")
        self._host_input.setEnabled(not connected and not connecting)
        self._port_input.setEnabled(not connected and not connecting)
        self._send_button.setEnabled(connected)
        self._command_input.setEnabled(connected)

    def _send_command(self) -> None:
        if not self._connection.is_connected():
            self._append_log("Not connected.")
            return
        command = self._command_input.text().strip()
        if not command:
            return
        try:
            self._connection.send_command(command)
        except RuntimeError:
            self._append_log("Failed to send command.")
            return
        self._append_log(f"> {command}")
        self._command_input.clear()

    def _append_log(self, message: str) -> None:
        self._log.appendPlainText(message)
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._log.setTextCursor(cursor)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Robot host or IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Serial bridge TCP port")
    args = parser.parse_args(list(argv) if argv is not None else None)

    app = QApplication(sys.argv)
    window = SerialBridgeClient(host=args.host, port=args.port)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
