"""Dedicated chassis control surface for the robot bridge."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from robot_control.remote_bridge import RemoteBridgeController


class BridgeChassisPanel(QWidget):
    """Large-format D-pad and presets for chassis motion."""

    def __init__(self, controller: RemoteBridgeController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._connected = controller.is_connected()
        self._throttle_label: QLabel | None = None
        self._throttle_slider: QSlider | None = None
        self._action_log: QPlainTextEdit | None = None
        self._controlled_sections: list[QWidget] = []

        self._build_ui()
        self._wire_controller()
        self._update_state_label(self._controller.state())
        self._apply_link_state(self._connected)

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("Chassis control")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel("Drive the rover with the D-pad, throttle, and motion presets.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.7);")
        layout.addWidget(subtitle)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.addWidget(QLabel("Link status:"))
        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("bridgeChassisStatus")
        status_row.addWidget(self._status_label, 1)
        layout.addLayout(status_row)

        layout.addWidget(self._register_section(self._build_throttle_strip()))
        layout.addWidget(self._register_section(self._build_dpad()))
        layout.addWidget(self._register_section(self._build_presets()))

        self._action_log = QPlainTextEdit()
        self._action_log.setReadOnly(True)
        self._action_log.setMaximumBlockCount(200)
        self._action_log.setPlaceholderText("Recent commands will appear here")
        self._action_log.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.05);"
            "border: 1px solid rgba(255, 255, 255, 0.08);"
            "border-radius: 8px;"
            "font-family: 'JetBrains Mono', 'Fira Code', monospace;"
        )
        layout.addWidget(self._action_log, 1)

    def _register_section(self, widget: QWidget) -> QWidget:
        self._controlled_sections.append(widget)
        return widget

    def _build_throttle_strip(self) -> QWidget:
        container = QGroupBox("Speed & trim")
        row = QHBoxLayout(container)
        row.setSpacing(12)
        row.addWidget(QLabel("Throttle"))

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(5, 50)  # 0.05 .. 0.50 per CMD_SPEED_CTRL spec
        slider.setValue(45)
        slider.valueChanged.connect(self._update_throttle_label)
        self._throttle_slider = slider
        row.addWidget(slider, 1)

        self._throttle_label = QLabel()
        self._throttle_label.setMinimumWidth(80)
        self._throttle_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._throttle_label)

        self._update_throttle_label(slider.value())
        return container

    def _build_dpad(self) -> QWidget:
        container = QGroupBox("Directional pad")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        container.setLayout(grid)

        def pad_button(label: str, callback: Callable[[], None]) -> QPushButton:
            button = QPushButton(label)
            button.setMinimumSize(72, 72)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "font-size: 18px;"
                "font-weight: 600;"
                "border-radius: 16px;"
                "padding: 12px;"
            )
            button.clicked.connect(callback)
            return button

        grid.addWidget(pad_button("NW", lambda: self._send_direction(-0.3, 1.0)), 0, 0)
        grid.addWidget(pad_button("N", lambda: self._send_direction(1.0, 1.0)), 0, 1)
        grid.addWidget(pad_button("NE", lambda: self._send_direction(1.0, 0.3)), 0, 2)
        grid.addWidget(pad_button("W", lambda: self._send_direction(-1.0, 1.0)), 1, 0)
        grid.addWidget(pad_button("STOP", self._send_stop), 1, 1)
        grid.addWidget(pad_button("E", lambda: self._send_direction(1.0, -1.0)), 1, 2)
        grid.addWidget(pad_button("SW", lambda: self._send_direction(-1.0, -0.3)), 2, 0)
        grid.addWidget(pad_button("S", lambda: self._send_direction(-1.0, -1.0)), 2, 1)
        grid.addWidget(pad_button("SE", lambda: self._send_direction(0.3, -1.0)), 2, 2)

        return container

    def _build_presets(self) -> QWidget:
        container = QGroupBox("Motion presets")
        container.setLayout(QVBoxLayout())
        container.layout().setSpacing(10)

        presets = [
            ("Cruise", 1.0, 1.0),
            ("Glide left", 0.6, 1.0),
            ("Glide right", 1.0, 0.6),
            ("Spin", 1.0, -1.0),
            ("Reverse arc", -0.4, -0.7),
            ("Pulse", 1.0, 1.0),
        ]

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        for label, left, right in presets:
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, l=left, r=right: self._execute_preset(l, r)
            )
            button_row.addWidget(button)

        container.layout().addLayout(button_row)
        hint = QLabel(
            "Presets use the current throttle (Wave Rover accepts ±0.50). Tap Stop to cancel motion."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 12px;")
        container.layout().addWidget(hint)
        return container

    # ------------------------------------------------------------------
    # Controller wiring
    # ------------------------------------------------------------------
    def _wire_controller(self) -> None:
        self._controller.connectionStateChanged.connect(self._handle_state_changed)
        self._controller.remoteActiveChanged.connect(self._handle_link_active)
        self._controller.errorOccurred.connect(
            lambda message: self._log_action(f"[ERROR] {message}")
        )

    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:
        self._update_state_label(state)

    def _handle_link_active(self, active: bool) -> None:
        self._connected = active
        self._apply_link_state(active)
        if not active:
            self._log_action("Bridge inactive - connect via Robot link tab")

    def _apply_link_state(self, active: bool) -> None:
        for widget in self._controlled_sections:
            widget.setEnabled(active)

    def _update_state_label(self, state: QAbstractSocket.SocketState) -> None:
        label = {
            QAbstractSocket.SocketState.UnconnectedState: "Disconnected",
            QAbstractSocket.SocketState.HostLookupState: "Resolving host",
            QAbstractSocket.SocketState.ConnectingState: "Connecting",
            QAbstractSocket.SocketState.ConnectedState: "Connected",
            QAbstractSocket.SocketState.ClosingState: "Closing",
        }.get(state, "Unknown")
        self._status_label.setText(label)

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    def _current_throttle(self) -> float:
        if self._throttle_slider is None:
            return 0.0
        return self._throttle_slider.value() / 100.0

    def _send_direction(self, left_factor: float, right_factor: float) -> None:
        throttle = self._current_throttle()
        payload = {
            "T": 1,
            "L": self._clamp_speed(left_factor * throttle),
            "R": self._clamp_speed(right_factor * throttle),
        }
        self._send_payload(payload, description=f"Drive L={payload['L']:+.2f} R={payload['R']:+.2f}")

    def _send_stop(self) -> None:
        self._send_payload({"T": 1, "L": 0.0, "R": 0.0}, description="Stop")

    def _execute_preset(self, left: float, right: float) -> None:
        throttle = self._current_throttle()
        payload = {
            "T": 1,
            "L": self._clamp_speed(left * throttle),
            "R": self._clamp_speed(right * throttle),
        }
        self._send_payload(payload, description=f"Preset L={payload['L']:+.2f} R={payload['R']:+.2f}")

    def _send_payload(self, payload: dict[str, float], *, description: str) -> None:
        try:
            self._controller.send_command(json.dumps(payload))
        except RuntimeError as exc:
            self._log_action(f"[ERROR] {exc}")
            return
        self._log_action(description)

    @staticmethod
    def _clamp_speed(value: float) -> float:
        """Clamp outgoing speeds to the documented ±0.5 range."""

        return round(max(-0.5, min(0.5, value)), 3)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _log_action(self, text: str) -> None:
        if self._action_log is None:
            return
        self._action_log.appendPlainText(text)
        bar = self._action_log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _update_throttle_label(self, value: int) -> None:
        if self._throttle_label is None:
            return
        percent = min(100, max(0, int((value / 50) * 100)))
        self._throttle_label.setText(f"{value / 100.0:.2f} speed ({percent}%)")
