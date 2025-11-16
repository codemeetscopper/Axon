from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Optional, Sequence

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel
from robot_control import (
    EmotionPolicy,
    FaceController,
    SerialCommandServer,
    SerialCommandServerConfig,
    SerialReader,
)
from robot_control.gyro_calibrator import GyroCalibrator
from simulation_main import FaceTelemetryDisplay

try:  # Reuse the palette from the interactive demo when available.
    from axon_ui import apply_dark_palette as apply_palette
except Exception:  # pragma: no cover - best effort reuse
    apply_palette = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


class RobotMainWindow(QWidget):
    def __init__(
        self,
        face: RoboticFaceWidget,
        overlays: Sequence[QWidget] | QWidget,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Axon Runtime")
        self._display = FaceTelemetryDisplay(
            face,
            overlays,
            parent=self,
            fixed_size=None,
        )
        self._register_info_controls(overlays)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._display)

    def _register_info_controls(self, overlays: Sequence[QWidget] | QWidget) -> None:
        widgets: Sequence[QWidget]
        if isinstance(overlays, Sequence):
            widgets = overlays
        else:
            widgets = (overlays,)
        for widget in widgets:
            if isinstance(widget, InfoPanel):
                widget.displayModeToggleRequested.connect(self._toggle_window_mode)

    def _toggle_window_mode(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()


class RobotRuntime(QWidget):
    """Manage the serial polling loop inside the Qt event loop."""

    def __init__(
        self,
        reader: SerialReader,
        controller: FaceController,
        telemetry: TelemetryPanel,
        poll_interval_ms: int = 40,
        parent: Optional[QWidget] = None,
        calibrator: GyroCalibrator | None = None,
    ) -> None:
        super().__init__(parent)
        self._reader = reader
        self._controller = controller
        self._telemetry = telemetry
        self._calibrator = calibrator or GyroCalibrator()
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
        self._calibrator.observe(sample)
        self._controller.apply_sample(sample)
        self._telemetry.update_sample(sample)


DEFAULT_SERIAL_PORT = "/dev/ttyAMA0"
DEFAULT_BAUDRATE = 115200
DEFAULT_POLL_INTERVAL_MS = 40
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_COMMAND_PORT = 8765


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    # Allow the hardware stack to settle before attempting to connect.
    time.sleep(5)
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
    command_server = SerialCommandServer(
        reader,
        config=SerialCommandServerConfig(port=DEFAULT_COMMAND_PORT),
    )
    command_server.start()

    controller = FaceController(face, EmotionPolicy())
    telemetry = TelemetryPanel()
    info_panel = InfoPanel()
    window = RobotMainWindow(face, (info_panel, telemetry))

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
    )
    app.aboutToQuit.connect(runtime.stop)
    app.aboutToQuit.connect(command_server.stop)

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
        command_server.stop()


if __name__ == "__main__":
    sys.exit(main())
