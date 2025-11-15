from __future__ import annotations

import random
import sys
from functools import partial
from typing import Callable

from PySide6.QtCore import Qt, QTimer
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
    QVBoxLayout,
    QWidget,
)

from app_palette import apply_dark_palette
from robot_control.sensor_data import SensorSample
from robot_main import TelemetryPanel
from robotic_face_widget import RoboticFaceWidget

# Backwards compatibility for external imports expecting the old helper name.
_apply_dark_palette = apply_dark_palette


class RobotDisplay(QFrame):
    """Composite widget that mimics the robot's screen."""

    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry: TelemetryPanel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._face = face
        self._telemetry = telemetry
        self._build_ui()

    def _build_ui(self) -> None:
        self.setObjectName("robotDisplay")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        face_holder = QFrame()
        face_holder.setObjectName("robotDisplayFace")
        face_holder.setFrameShape(QFrame.Shape.NoFrame)
        face_layout = QVBoxLayout(face_holder)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(0)
        face_layout.addWidget(self._face, 1)
        layout.addWidget(face_holder, 1)

        telemetry_holder = QWidget()
        telemetry_holder.setObjectName("robotDisplayTelemetry")
        telemetry_layout = QHBoxLayout(telemetry_holder)
        telemetry_layout.setContentsMargins(0, 0, 0, 0)
        telemetry_layout.setSpacing(0)
        telemetry_layout.addWidget(self._telemetry, 1)
        layout.addWidget(telemetry_holder, 0)

        self.setStyleSheet(
            """
            #robotDisplay {
                background-color: rgba(6, 10, 24, 0.82);
                border-radius: 28px;
                border: 2px solid rgba(78, 112, 168, 0.35);
            }
            #robotDisplayFace {
                background-color: rgba(2, 5, 15, 0.9);
                border-radius: 22px;
            }
            #robotDisplayFace > QWidget {
                border-radius: 22px;
            }
            #robotDisplayTelemetry {
                padding-top: 6px;
            }
            """
        )


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
        self.telemetry.expand()

        display = RobotDisplay(self.face, self.telemetry)
        layout.addWidget(display, 3)

        panel = ControlPanel(self.face, self.telemetry)
        panel.setFixedWidth(280)
        panel.setObjectName("controlPanel")
        layout.addWidget(panel, 1)

        self.face.set_emotion("happy")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    window = MainWindow()
    window.resize(1100, 680)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
