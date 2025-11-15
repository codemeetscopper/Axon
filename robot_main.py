from __future__ import annotations

import logging
import signal
import sys
from typing import Callable, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
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


Formatter = Callable[[float], str]


class TelemetryPanel(QFrame):
    """Display the latest telemetry sample."""

    _FIELDS: tuple[tuple[str, str, Formatter, str], ...] = (
        ("left_speed", "◀", lambda value: f"{value:.0f}", "#4CC9F0"),
        ("right_speed", "▶", lambda value: f"{value:.0f}", "#4895EF"),
        ("roll", "⟳", lambda value: f"{value:+.1f}°", "#4361EE"),
        ("pitch", "↕", lambda value: f"{value:+.1f}°", "#560BAD"),
        ("yaw", "◎", lambda value: f"{value:+.1f}°", "#B5179E"),
        ("temperature_c", "☀", lambda value: f"{value:.1f}°C", "#F72585"),
        ("voltage_v", "⚡", lambda value: f"{value:.2f}V", "#2DD881"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value_labels: dict[str, QLabel] = {}
        self._formatters: dict[str, Formatter] = {}
        self._status_icon = QLabel("●")
        self._status_icon.setObjectName("telemetryStatus")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("telemetryPanel")
        self._build_ui()
        self.set_streaming(False)

    def _build_ui(self) -> None:
        self.setFixedHeight(56)
        self.setStyleSheet(
            "#telemetryPanel {"
            "background: rgba(6, 10, 24, 0.92);"
            "border-top: 1px solid rgba(120, 150, 220, 0.25);"
            "}"
            "#telemetryPanel QLabel {"
            "color: #e8f1ff;"
            "font-size: 17px;"
            "font-weight: 600;"
            "}"
            "#telemetryPanel QLabel#telemetryStatus {"
            "font-size: 16px;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(12)

        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._status_icon.setFixedWidth(20)
        layout.addWidget(self._status_icon)

        for field, icon, formatter, color in self._FIELDS:
            try:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
            except (ValueError, IndexError):
                r, g, b = (76, 201, 240)
            container = QFrame()
            container.setObjectName("telemetryItem")
            container.setProperty("dataRole", field)
            container.setStyleSheet(
                "QFrame#telemetryItem {"
                f"background-color: rgba({r}, {g}, {b}, 0.18);"
                "border-radius: 14px;"
                "padding: 6px 10px;"
                "}"
            )
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(8, 2, 8, 2)
            container_layout.setSpacing(6)

            icon_label = QLabel(icon)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            icon_label.setStyleSheet(
                f"color: {color}; font-size: 20px; font-weight: 600;"
            )
            container_layout.addWidget(icon_label)

            value_label = QLabel("--")
            value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value_label.setStyleSheet(
                f"color: {color}; font-size: 18px; font-weight: 600;"
            )
            container_layout.addWidget(value_label)

            layout.addWidget(container)
            self._value_labels[field] = value_label
            self._formatters[field] = formatter

        layout.addStretch(1)

    def update_sample(self, sample: SensorSample) -> None:
        values = sample.as_dict()
        for field, label in self._value_labels.items():
            value = values.get(field)
            formatter = self._formatters.get(field, lambda v: str(v))
            if value is None:
                label.setText("--")
            else:
                label.setText(formatter(value))
        self.set_streaming(True)

    def set_streaming(self, streaming: bool) -> None:
        color = "#2DD881" if streaming else "#7A8194"
        self._status_icon.setText("●")
        self._status_icon.setStyleSheet(f"color: {color};")
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

        face.setParent(self)
        face.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(face, 1)

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
