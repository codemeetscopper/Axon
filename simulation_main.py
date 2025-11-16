from __future__ import annotations

import random
import sys
from functools import partial
from typing import Callable, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, QWIDGETSIZE_MAX
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSpinBox,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel, apply_dark_palette
from robot_control.remote_bridge import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    RemoteBridgeController,
)
from robot_control.sensor_data import SensorSample

# Backwards compatibility for external imports expecting the old helper name.
_apply_dark_palette = apply_dark_palette


class FaceTelemetryDisplay(QWidget):
    """Composite widget that overlays telemetry/info controls on the face widget."""

    def __init__(
        self,
        face: RoboticFaceWidget,
        overlays: Sequence[QWidget] | QWidget,
        parent: QWidget | None = None,
        fixed_size: QSize | Sequence[int] | None = QSize(800, 480),
    ) -> None:
        super().__init__(parent)
        self._face = face
        if isinstance(overlays, Sequence):
            self._overlay_widgets = tuple(overlays)
        else:
            self._overlay_widgets = (overlays,)
        self._fixed_size = fixed_size
        self._collapsible_panels: list[QWidget] = []
        self._telemetry_panel = next(
            (widget for widget in self._overlay_widgets if isinstance(widget, TelemetryPanel)),
            None,
        )
        self._info_panel = next(
            (widget for widget in self._overlay_widgets if isinstance(widget, InfoPanel)),
            None,
        )
        self._overlay_dock: QWidget | None = None
        self._dock_layout: QHBoxLayout | None = None
        self._overlay_margin = 16
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("robotScreen")
        if self._fixed_size is not None:
            if isinstance(self._fixed_size, QSize):
                size = self._fixed_size
            else:
                width, height = self._fixed_size
                size = QSize(int(width), int(height))
            self.setFixedSize(size)
        else:
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        stack = QStackedLayout(self)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        face_layer = QFrame(self)
        face_layer.setObjectName("robotScreenFace")
        face_layout = QVBoxLayout(face_layer)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(0)
        self._face.setParent(face_layer)
        self._face.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        face_layout.addWidget(self._face)
        stack.addWidget(face_layer)

        overlay = QWidget(self)
        overlay.setObjectName("robotScreenOverlay")
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(
            self._overlay_margin, self._overlay_margin, self._overlay_margin, self._overlay_margin
        )
        overlay_layout.setSpacing(0)

        dock = QWidget(overlay)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(10)
        dock_layout.addStretch(1)
        for widget in self._overlay_widgets:
            if widget is self._telemetry_panel:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                dock_layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignTop)
            else:
                widget.setSizePolicy(
                    QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
                )
                dock_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)
        overlay_layout.addWidget(dock, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._overlay_dock = dock
        self._dock_layout = dock_layout
        overlay_layout.addStretch(1)
        self._register_collapsible_panels()
        stack.addWidget(overlay)

        # Ensure the overlay paints above the face layer when the layout is in
        # ``StackAll`` mode. Without explicitly raising the overlay, Qt keeps the
        # face frame as the top-most widget, which hides the telemetry bar.
        stack.setCurrentWidget(face_layer)
        overlay.raise_()

        self.setStyleSheet(
            """
            #robotScreen {
                background-color: #040914;
                border-radius: 20px;
                border: 1px solid rgba(68, 88, 128, 0.45);
            }
            #robotScreenFace > QWidget {
                border-radius: 20px;
            }
            #robotScreenOverlay {
                background: transparent;
            }
            """
        )

        self._update_overlay_geometry()

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._update_overlay_geometry()

    def _register_collapsible_panels(self) -> None:
        self._collapsible_panels = []
        for widget in self._overlay_widgets:
            signal = getattr(widget, "collapsedChanged", None)
            if signal is None:
                continue
            self._collapsible_panels.append(widget)
            signal.connect(partial(self._handle_panel_toggle, widget))
            signal.connect(lambda *_: self._update_overlay_geometry())

    def _handle_panel_toggle(self, source: QWidget, collapsed: bool) -> None:
        if collapsed:
            return
        for panel in self._collapsible_panels:
            if panel is source:
                continue
            collapse = getattr(panel, "collapse", None)
            is_collapsed = getattr(panel, "is_collapsed", None)
            if callable(collapse) and callable(is_collapsed) and not is_collapsed():
                collapse()
        self._update_overlay_geometry()

    def _update_overlay_geometry(self) -> None:
        if self._overlay_dock is None:
            return
        available_width = max(0, self.width() - 2 * self._overlay_margin)
        self._overlay_dock.setFixedWidth(available_width)
        extras = [
            widget
            for widget in self._overlay_widgets
            if widget is not self._telemetry_panel
        ]
        reserved = 0
        for widget in extras:
            panel_width = self._panel_width(widget)
            self._set_panel_width(widget, panel_width)
            reserved += panel_width
        spacing = (self._dock_layout.spacing() if self._dock_layout is not None else 0)
        reserved += spacing * len(extras)

        if self._telemetry_panel is None:
            return

        collapsed_width = self._telemetry_panel.collapsed_width()
        if self._telemetry_panel.is_collapsed():
            width = collapsed_width
        else:
            width = max(collapsed_width, available_width - reserved)
        self._set_panel_width(self._telemetry_panel, width)

    @staticmethod
    def _set_panel_width(panel: QWidget, width: int) -> None:
        width = max(0, int(width))
        panel.setMinimumWidth(width)
        panel.setMaximumWidth(max(width, QWIDGETSIZE_MAX))

    @staticmethod
    def _panel_width(panel: QWidget) -> int:
        is_collapsed = getattr(panel, "is_collapsed", None)
        collapsed_width = getattr(panel, "collapsed_width", None)
        if callable(is_collapsed) and is_collapsed() and callable(collapsed_width):
            return int(collapsed_width())
        hint = panel.sizeHint()
        return max(0, hint.width())


class RemoteBridgeWidget(QFrame):
    """Small utility panel that connects to the real robot."""

    def __init__(self, bridge: RemoteBridgeController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self.setObjectName("remoteBridgePanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "#remoteBridgePanel {"
            "  background-color: rgba(4, 9, 20, 0.72);"
            "  border: 1px solid rgba(255, 255, 255, 0.08);"
            "  border-radius: 12px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Robot link")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._host_input = QLineEdit(DEFAULT_BRIDGE_HOST)
        self._host_input.setPlaceholderText("Robot IP address")
        self._host_input.setClearButtonEnabled(True)
        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(DEFAULT_BRIDGE_PORT)
        self._connect_button = QPushButton("Connect")
        self._connect_button.clicked.connect(self._toggle_connection)
        self._status_label = QLabel("Offline")
        self._status_label.setStyleSheet("color: #f94144; font-weight: 600;")

        row.addWidget(QLabel("Host:"))
        row.addWidget(self._host_input, 2)
        row.addWidget(QLabel("Port:"))
        row.addWidget(self._port_input)
        row.addWidget(self._connect_button)
        row.addWidget(self._status_label)
        layout.addLayout(row)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #f9c74f; font-size: 12px;")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        self._bridge.connectionStateChanged.connect(self._handle_state_change)
        self._bridge.errorOccurred.connect(self._show_error)
        self._update_controls()

    def _toggle_connection(self) -> None:
        state = self._bridge.state()
        if state in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        ):
            self._bridge.disconnect()
            return
        host = self._host_input.text().strip() or DEFAULT_BRIDGE_HOST
        port = int(self._port_input.value())
        self._error_label.clear()
        self._bridge.connect_to(host, port)
        self._update_controls()

    def _handle_state_change(self, state: QAbstractSocket.SocketState) -> None:
        if state == QAbstractSocket.SocketState.ConnectedState:
            text, color = "Connected", "#2dd881"
            button = "Disconnect"
        elif state == QAbstractSocket.SocketState.ConnectingState:
            text, color = "Connecting...", "#ffd166"
            button = "Cancel"
        else:
            text, color = "Offline", "#f94144"
            button = "Connect"
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self._connect_button.setText(button)
        if state != QAbstractSocket.SocketState.UnconnectedState:
            self._error_label.clear()
        self._update_controls()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)

    def _update_controls(self) -> None:
        state = self._bridge.state()
        busy = state in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        )
        self._host_input.setEnabled(not busy)
        self._port_input.setEnabled(not busy)
class ControlPanel(QWidget):
    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        *,
        remote_bridge: RemoteBridgeController | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.face = face
        self.telemetry = telemetry
        self._remote_bridge = remote_bridge
        self._remote_active = False
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(2600)
        self._cycle_timer.timeout.connect(self._advance_cycle)
        self._telemetry_values: dict[str, float] = {
            "message_type": 1001.0,
            "left_speed": 0.0,
            "right_speed": 0.0,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "temperature_c": 24.0,
            "voltage_v": 12.0,
        }
        self.sliders: dict[str, QSlider] = {}
        self._telemetry_sliders: dict[str, QSlider] = {}
        self._reset_button: QPushButton | None = None
        self._shuffle_button: QPushButton | None = None
        self._build_ui()
        self._push_telemetry()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        if self._remote_bridge is not None:
            remote_panel = RemoteBridgeWidget(self._remote_bridge)
            layout.addWidget(remote_panel)
            layout.addSpacing(12)
            self._remote_bridge.remoteActiveChanged.connect(self._handle_remote_active)

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
            slider.setValue(int(self._telemetry_values[axis]))
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
        self._reset_button = reset_btn

        shuffle_btn = QPushButton("Surprise Me ✨")
        shuffle_btn.clicked.connect(self._random_emotion)
        layout.addWidget(shuffle_btn)
        self._shuffle_button = shuffle_btn

        layout.addSpacing(18)

        telemetry_title = QLabel("Telemetry simulation")
        telemetry_title.setStyleSheet("font-size: 18px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(telemetry_title)

        telemetry_grid = QGridLayout()
        telemetry_grid.setVerticalSpacing(16)
        telemetry_grid.setHorizontalSpacing(12)
        telemetry_grid.setColumnStretch(1, 1)
        layout.addLayout(telemetry_grid)

        self._create_telemetry_slider(
            telemetry_grid,
            0,
            "Left speed",
            "left_speed",
            -255.0,
            255.0,
            1.0,
            lambda value: f"{value:.0f}",
        )
        self._create_telemetry_slider(
            telemetry_grid,
            1,
            "Right speed",
            "right_speed",
            -255.0,
            255.0,
            1.0,
            lambda value: f"{value:.0f}",
        )
        self._create_telemetry_slider(
            telemetry_grid,
            2,
            "Temperature",
            "temperature_c",
            0.0,
            100.0,
            0.1,
            lambda value: f"{value:.1f}°C",
        )
        self._create_telemetry_slider(
            telemetry_grid,
            3,
            "Voltage",
            "voltage_v",
            0.0,
            24.0,
            0.1,
            lambda value: f"{value:.1f}V",
        )

        layout.addSpacerItem(QSpacerItem(20, 40))

        tip = QLabel("Use the controls to explore the face and the telemetry overlay.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 12px;")
        layout.addWidget(tip)

        layout.addStretch(1)

    def _set_value_label(self, object_name: str, text: str) -> None:
        label = self.findChild(QLabel, object_name)
        if label is not None:
            label.setText(text)

    def _update_orientation(self, axis: str, value: int) -> None:
        if self._remote_active:
            return
        self.face.set_orientation(**{axis: float(value)})
        self._telemetry_values[axis] = float(value)
        self._set_value_label(f"value_{axis}", f"{value}°")
        self._push_telemetry()

    def _reset_orientation(self) -> None:
        if self._remote_active:
            return
        self.face.set_orientation(yaw=0.0, pitch=0.0, roll=0.0)
        for axis, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            self._telemetry_values[axis] = 0.0
            self._set_value_label(f"value_{axis}", "0°")
        self._push_telemetry()

    def _random_emotion(self) -> None:
        if self._remote_active:
            return
        emotions = list(self.face.available_emotions())
        if not emotions:
            return
        current_text = self.emotion_combo.currentText()
        choices = [emotion for emotion in emotions if emotion != current_text]
        next_emotion = random.choice(choices or emotions)
        self.emotion_combo.setCurrentText(next_emotion)

    def _toggle_cycle(self, enabled: bool) -> None:
        if self._remote_active:
            self.cycle_checkbox.blockSignals(True)
            self.cycle_checkbox.setChecked(False)
            self.cycle_checkbox.blockSignals(False)
            return
        if enabled and len(self.face.available_emotions()) > 1:
            self._cycle_timer.start()
        else:
            self._cycle_timer.stop()

    def _advance_cycle(self) -> None:
        if self._remote_active:
            return
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

    def _create_telemetry_slider(
        self,
        grid: QGridLayout,
        row: int,
        title: str,
        key: str,
        minimum: float,
        maximum: float,
        scale: float,
        formatter: Callable[[float], str],
    ) -> None:
        label = QLabel(title)
        label.setStyleSheet("font-size: 14px; font-weight: 500;")
        grid.addWidget(label, row, 0)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider_min = int(round(minimum / scale))
        slider_max = int(round(maximum / scale))
        slider.setRange(slider_min, slider_max)
        slider.setSingleStep(1)
        slider.setValue(int(round(self._telemetry_values[key] / scale)))
        slider.valueChanged.connect(
            partial(self._handle_telemetry_slider, key, scale, formatter)
        )
        grid.addWidget(slider, row, 1)
        self._telemetry_sliders[key] = slider

        value_label = QLabel(formatter(self._telemetry_values[key]))
        value_label.setObjectName(f"telemetry_value_{key}")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value_label.setFixedWidth(78)
        grid.addWidget(value_label, row, 2)

    def _handle_telemetry_slider(
        self,
        key: str,
        scale: float,
        formatter: Callable[[float], str],
        value: int,
    ) -> None:
        if self._remote_active:
            return
        actual = float(value) * scale
        self._telemetry_values[key] = actual
        self._set_value_label(f"telemetry_value_{key}", formatter(actual))
        self._push_telemetry()

    def _push_telemetry(self) -> None:
        if self._remote_active:
            return
        sample = SensorSample(
            message_type=int(self._telemetry_values["message_type"]),
            left_speed=float(self._telemetry_values["left_speed"]),
            right_speed=float(self._telemetry_values["right_speed"]),
            roll=float(self._telemetry_values["roll"]),
            pitch=float(self._telemetry_values["pitch"]),
            yaw=float(self._telemetry_values["yaw"]),
            temperature_c=float(self._telemetry_values["temperature_c"]),
            voltage_v=float(self._telemetry_values["voltage_v"]),
        )
        self.telemetry.update_sample(sample)

    def _handle_remote_active(self, active: bool) -> None:
        if self._remote_active == active:
            return
        self._remote_active = active
        if active:
            self._set_manual_controls_enabled(False)
            self._cycle_timer.stop()
            self.cycle_checkbox.blockSignals(True)
            self.cycle_checkbox.setChecked(False)
            self.cycle_checkbox.blockSignals(False)
        else:
            self._set_manual_controls_enabled(True)
            self._push_telemetry()

    def _set_manual_controls_enabled(self, enabled: bool) -> None:
        self.emotion_combo.setEnabled(enabled)
        self.cycle_checkbox.setEnabled(enabled)
        if self._reset_button is not None:
            self._reset_button.setEnabled(enabled)
        if self._shuffle_button is not None:
            self._shuffle_button.setEnabled(enabled)
        for slider in self.sliders.values():
            slider.setEnabled(enabled)
        for slider in self._telemetry_sliders.values():
            slider.setEnabled(enabled)


class MainWindow(QWidget):
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
        self.remote_bridge = RemoteBridgeController(self.face, self.telemetry)

        display = FaceTelemetryDisplay(self.face, (self.info_panel, self.telemetry))
        layout.addWidget(display, 0, Qt.AlignmentFlag.AlignTop)

        panel = ControlPanel(self.face, self.telemetry, remote_bridge=self.remote_bridge)
        panel.setFixedWidth(280)
        panel.setObjectName("controlPanel")
        layout.addWidget(panel, 1)

        self.face.set_emotion("happy")

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    window = MainWindow()
    window.resize(1220, 620)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
