from __future__ import annotations

import logging
import signal
import sys
import time

from PySide6.QtWidgets import QApplication

from axon_ros.runtime import RobotMainWindow, RobotRuntime
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel
from robot_control import EmotionPolicy, FaceController, SerialReader
from robot_control.serial_bridge_config import SerialBridgeConfig
from robot_control.serial_bridge_server import SerialBridgeServer

try:  # Reuse the palette from the interactive demo when available.
    from axon_ui import apply_dark_palette as apply_palette
except Exception:  # pragma: no cover - best effort reuse
    apply_palette = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

DEFAULT_SERIAL_PORT = "/dev/ttyAMA0"
DEFAULT_BAUDRATE = 115200
DEFAULT_POLL_INTERVAL_MS = 40
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_BRIDGE_HOST = "0.0.0.0"
DEFAULT_BRIDGE_PORT = 8765


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

    bridge = SerialBridgeServer(
        reader,
        config=SerialBridgeConfig(host=DEFAULT_BRIDGE_HOST, port=DEFAULT_BRIDGE_PORT),
    )

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Runtime")
    app.setStyle("Fusion")

    if apply_palette is not None:
        apply_palette(app)

    face = RoboticFaceWidget()
    controller = FaceController(face, EmotionPolicy())
    telemetry = TelemetryPanel()
    info_panel = InfoPanel()
    window = RobotMainWindow(face, (info_panel, telemetry))

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
        bridge=bridge,
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
