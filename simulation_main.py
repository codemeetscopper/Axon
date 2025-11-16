from __future__ import annotations

import random
import sys
from functools import partial
from typing import Callable, Sequence

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpacerItem,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel, apply_dark_palette
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
        panel.setMaximumWidth(width)

    @staticmethod
    def _panel_width(panel: QWidget) -> int:
        is_collapsed = getattr(panel, "is_collapsed", None)
        collapsed_width = getattr(panel, "collapsed_width", None)
        if callable(is_collapsed) and is_collapsed() and callable(collapsed_width):
            return int(collapsed_width())
        hint = panel.sizeHint()
        return max(0, hint.width())


class ControlPanel(QWidget):
    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.face = face
        self.telemetry = telemetry
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
        self._build_ui()
        self._push_telemetry()

    def _build_ui(self) -> None:
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

        shuffle_btn = QPushButton("Surprise Me ✨")
        shuffle_btn.clicked.connect(self._random_emotion)
        layout.addWidget(shuffle_btn)

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
        self.face.set_orientation(**{axis: float(value)})
        self._telemetry_values[axis] = float(value)
        self._set_value_label(f"value_{axis}", f"{value}°")
        self._push_telemetry()

    def _reset_orientation(self) -> None:
        self.face.set_orientation(yaw=0.0, pitch=0.0, roll=0.0)
        for axis, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            self._telemetry_values[axis] = 0.0
            self._set_value_label(f"value_{axis}", "0°")
        self._push_telemetry()

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
        actual = float(value) * scale
        self._telemetry_values[key] = actual
        self._set_value_label(f"telemetry_value_{key}", formatter(actual))
        self._push_telemetry()

    def _push_telemetry(self) -> None:
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
