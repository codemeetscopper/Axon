from __future__ import annotations

import logging
import signal
import sys
from typing import Callable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from robot_control import EmotionPolicy, FaceController, SerialReader
from robot_control.sensor_data import SensorSample
from robotic_face_widget import RoboticFaceWidget

try:  # Reuse the palette from the interactive demo when available.
    from main import _apply_dark_palette as apply_palette
except Exception:  # pragma: no cover - best effort reuse
    apply_palette = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


Formatter = Callable[[float], str]


class TelemetryPanel(QFrame):
    """Display the latest telemetry sample."""

    _FIELDS: tuple[tuple[str, str, Formatter], ...] = (
        ("left_speed", "⬅️", lambda value: f"{value:.0f}"),
        ("right_speed", "➡️", lambda value: f"{value:.0f}"),
        ("roll", "🌀", lambda value: f"{value:+.1f}°"),
        ("pitch", "↕️", lambda value: f"{value:+.1f}°"),
        ("yaw", "🧭", lambda value: f"{value:+.1f}°"),
        ("temperature_c", "🌡️", lambda value: f"{value:.1f}°C"),
        ("voltage_v", "🔋", lambda value: f"{value:.2f}V"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._formatters: dict[str, Formatter] = {}
        self._icons: dict[str, str] = {}
        self._status_icon = QLabel("⚫")
        self.setObjectName("telemetryPanel")
        self._build_ui()
        self.set_streaming(False)

    def _build_ui(self) -> None:
        self.setFixedHeight(72)
        self.setStyleSheet(
            "#telemetryPanel {"
            "background: rgba(6, 10, 24, 0.92);"
            "border-top: 1px solid rgba(120, 150, 220, 0.25);"
            "}"
            "#telemetryPanel QLabel {"
            "color: #e8f1ff;"
            "font-size: 18px;"
            "font-weight: 600;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(20)

        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status_icon)

        for field, icon, formatter in self._FIELDS:
            label = QLabel(f"{icon} --")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName(f"telemetry_{field}")
            layout.addWidget(label)
            self._labels[field] = label
            self._formatters[field] = formatter
            self._icons[field] = icon

        layout.addStretch(1)

    def update_sample(self, sample: SensorSample) -> None:
        values = sample.as_dict()
        for field, label in self._labels.items():
            value = values.get(field)
            formatter = self._formatters.get(field, lambda v: str(v))
            icon = self._icons.get(field, "")
            if value is None:
                label.setText(f"{icon} --")
            else:
                label.setText(f"{icon} {formatter(value)}")
        self.set_streaming(True)

    def set_streaming(self, streaming: bool) -> None:
        self._status_icon.setText("🟢" if streaming else "⚫")
        self._status_icon.setToolTip("Streaming" if streaming else "Idle")


class RobotMainWindow(QWidget):
    def __init__(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        super().__init__()
        self.setWindowTitle("Axon Runtime")
        self._build_ui(face, telemetry)

    def _build_ui(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        face_frame = QFrame()
        face_frame.setFrameShape(QFrame.Shape.NoFrame)
        face_layout = QVBoxLayout(face_frame)
        face_layout.setContentsMargins(24, 24, 24, 12)
        face_layout.setSpacing(0)
        face_layout.addStretch(1)
        face_layout.addWidget(face, alignment=Qt.AlignmentFlag.AlignCenter)
        face_layout.addStretch(1)
        layout.addWidget(face_frame, 1)
        layout.setStretchFactor(face_frame, 1)

        telemetry.setParent(self)
        layout.addWidget(telemetry, 0)
        layout.setStretchFactor(telemetry, 0)


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
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._reader.start()
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            self._reader.stop()
            return
        self._running = False
        self._timer.stop()
        self._reader.stop()

    def _poll(self) -> None:
        sample = self._reader.pop_latest()
        if sample is None:
            self._missed_cycles += 1
            if self._missed_cycles >= 10:
                self._telemetry.set_streaming(False)
            return

        self._missed_cycles = 0
        self._controller.apply_sample(sample)
        self._telemetry.update_sample(sample)


DEFAULT_SERIAL_PORT = "/dev/ttyAMA0"
DEFAULT_BAUDRATE = 115200
DEFAULT_POLL_INTERVAL_MS = 40
DEFAULT_LOG_LEVEL = "INFO"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    _configure_logging(DEFAULT_LOG_LEVEL)

    try:
        reader = SerialReader(port=DEFAULT_SERIAL_PORT, baudrate=DEFAULT_BAUDRATE)
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

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
    )
    app.aboutToQuit.connect(runtime.stop)

    # Support clean shutdown when Ctrl+C is pressed on the console.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    runtime.start()
    window.showFullScreen()

    try:
        return app.exec()
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received; shutting down.")
        app.quit()
        return 0
    finally:
        runtime.stop()


if __name__ == "__main__":
    sys.exit(main())
