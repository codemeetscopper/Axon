from __future__ import annotations

import argparse
import logging
import signal
import sys
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from robot_control import EmotionPolicy, FaceController, SerialReader
from robot_control.sensor_data import SensorSample
from robotic_face_widget import RoboticFaceWidget

try:  # Reuse the palette from the interactive demo when available.
    from main import _apply_dark_palette as apply_palette
except Exception:  # pragma: no cover - best effort reuse
    apply_palette = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


class TelemetryPanel(QWidget):
    """Display the latest telemetry sample."""

    _FIELD_TITLES = {
        "timestamp_ms": "Timestamp",
        "left_speed": "Left motor",
        "right_speed": "Right motor",
        "roll": "Roll",
        "pitch": "Pitch",
        "yaw": "Yaw",
        "temperature_c": "Temp",
        "voltage_v": "Voltage",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._status = QLabel("Waiting for data…")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Axon Telemetry")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        self._status.setStyleSheet("color: rgba(255,255,255,0.7);")
        layout.addWidget(self._status)

        grid = QGridLayout()
        grid.setVerticalSpacing(10)
        grid.setHorizontalSpacing(12)
        layout.addLayout(grid)

        for row, (field, label_text) in enumerate(self._FIELD_TITLES.items()):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setStyleSheet("font-weight: 500;")
            grid.addWidget(label, row, 0)

            value = QLabel("--")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setObjectName(f"telemetry_{field}")
            grid.addWidget(value, row, 1)
            self._labels[field] = value

        layout.addSpacerItem(QSpacerItem(20, 20))
        layout.addStretch(1)

    def update_sample(self, sample: SensorSample) -> None:
        values = sample.as_dict()
        values["roll"] = f"{values['roll']:+.1f}°"
        values["pitch"] = f"{values['pitch']:+.1f}°"
        values["yaw"] = f"{values['yaw']:+.1f}°"
        values["temperature_c"] = f"{values['temperature_c']:.1f} °C"
        values["voltage_v"] = f"{values['voltage_v']:.2f} V"
        values["left_speed"] = f"{values['left_speed']:.0f}"
        values["right_speed"] = f"{values['right_speed']:.0f}"
        for field, label in self._labels.items():
            label.setText(str(values.get(field, "--")))
        self.set_streaming(True)

    def set_streaming(self, streaming: bool) -> None:
        self._status.setText("Streaming data" if streaming else "Waiting for data…")
        self._status.setStyleSheet(
            "color: rgba(120,255,200,0.9);" if streaming else "color: rgba(255,255,255,0.7);"
        )


class RobotMainWindow(QWidget):
    def __init__(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        super().__init__()
        self.setWindowTitle("Axon Runtime")
        self._build_ui(face, telemetry)

    def _build_ui(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        face_frame = QFrame()
        face_frame.setFrameShape(QFrame.Shape.NoFrame)
        face_layout = QVBoxLayout(face_frame)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.addWidget(face)
        layout.addWidget(face_frame, 4)

        telemetry.setFixedWidth(260)
        telemetry.setObjectName("telemetryPanel")
        layout.addWidget(telemetry, 1)


class RobotRuntime(QWidget):
    """Manage the serial polling loop inside the Qt event loop."""

    def __init__(
        self,
        reader: SerialReader,
        controller: FaceController,
        telemetry: TelemetryPanel,
        poll_interval_ms: int = 40,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._reader = reader
        self._controller = controller
        self._telemetry = telemetry
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)
        self._missed_cycles = 0

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._reader.close()

    def _poll(self) -> None:
        sample = self._reader.read_latest()
        if sample is None:
            self._missed_cycles += 1
            if self._missed_cycles >= 10:
                self._telemetry.set_streaming(False)
            return

        self._missed_cycles = 0
        self._controller.apply_sample(sample)
        self._telemetry.update_sample(sample)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Axon runtime that drives the robotic face")
    parser.add_argument("--port", default="/dev/ttyAMA0", help="Serial port that streams Axon telemetry")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baud rate")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=40,
        help="Polling interval in milliseconds for the serial connection",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)

    try:
        reader = SerialReader(port=args.port, baudrate=args.baudrate)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Runtime")
    app.setStyle("Fusion")

    if apply_palette is not None:
        apply_palette(app)

    face = RoboticFaceWidget()
    controller = FaceController(face, EmotionPolicy())
    telemetry = TelemetryPanel()
    window = RobotMainWindow(face, telemetry)

    runtime = RobotRuntime(reader, controller, telemetry, poll_interval_ms=args.poll_interval)
    app.aboutToQuit.connect(runtime.stop)

    # Support clean shutdown when Ctrl+C is pressed on the console.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    runtime.start()
    window.resize(960, 600)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
