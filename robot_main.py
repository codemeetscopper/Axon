from __future__ import annotations

import logging
import signal
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from axon_ros.osi import OsiLayer, OsiStack, describe_stack
from axon_ros.runtime import RobotMainWindow, RobotRuntime
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel
from panandtilt import PanTiltController, PanTiltGimbalController
from robot_control import EmotionPolicy, FaceController, GyroCalibrator, SerialReadWriter
from robot_control.serial_bridge_config import SerialBridgeConfig
from robot_control.serial_bridge_server import SerialBridgeServer
from robot_control.video_stream_server import VideoStreamServer

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
DEFAULT_VIDEO_PORT = 8770


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def _schedule_video_stream(app: QApplication, stack: OsiStack) -> None:
    def _start() -> None:
        from robot_control.video_stream_server import VideoStreamServer

        server = VideoStreamServer(host=DEFAULT_BRIDGE_HOST, port=DEFAULT_VIDEO_PORT)
        stack.register(
            OsiLayer.TRANSPORT,
            "VideoStreamServer",
            server,
            description="USB camera stream",
        )
        if server.start():
            LOGGER.info("Video stream server listening on %s:%s", DEFAULT_BRIDGE_HOST, DEFAULT_VIDEO_PORT)
        else:
            LOGGER.warning(
                "Video stream server failed to start on %s:%s",
                DEFAULT_BRIDGE_HOST,
                DEFAULT_VIDEO_PORT,
            )
        app.aboutToQuit.connect(server.stop)

    QTimer.singleShot(0, _start)


def main() -> int:
    # Allow the hardware stack to settle before attempting to connect.
    time.sleep(5)
    _configure_logging(DEFAULT_LOG_LEVEL)

    stack = OsiStack("Robot runtime")

    try:
        reader = SerialReadWriter(port=DEFAULT_SERIAL_PORT, baudrate=DEFAULT_BAUDRATE)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1
    stack.register(
        OsiLayer.PHYSICAL,
        "SerialReadWriter",
        reader,
        description="UART sensor feed",
    )

    bridge = SerialBridgeServer(
        reader,
        config=SerialBridgeConfig(host=DEFAULT_BRIDGE_HOST, port=DEFAULT_BRIDGE_PORT),
    )
    stack.register(
        OsiLayer.TRANSPORT,
        "SerialBridgeServer",
        bridge,
        description="TCP telemetry bridge",
    )
    video_stream = VideoStreamServer(host=DEFAULT_BRIDGE_HOST, port=DEFAULT_VIDEO_PORT)
    if video_stream.start():
        stack.register(
            OsiLayer.TRANSPORT,
            "VideoStreamServer",
            video_stream,
            description="USB camera stream",
        )
    else:
        LOGGER.warning("Video stream server failed to start on %s:%s", DEFAULT_BRIDGE_HOST, DEFAULT_VIDEO_PORT)

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Runtime")
    app.setStyle("Fusion")

    if apply_palette is not None:
        apply_palette(app)

    _schedule_video_stream(app, stack)

    face = RoboticFaceWidget()
    policy = EmotionPolicy()
    calibrator = GyroCalibrator()
    controller = FaceController(face, policy)
    gimbal_controller = None
    try:
        gimbal_controller = PanTiltGimbalController(PanTiltController())
        stack.register(OsiLayer.PRESENTATION, "PanTiltGimbalController", gimbal_controller)
    except Exception as exc:
        LOGGER.warning("Pan/tilt controller unavailable: %s", exc)
    telemetry = TelemetryPanel()
    info_panel = InfoPanel()
    window = RobotMainWindow(face, (info_panel, telemetry))
    stack.register(OsiLayer.PRESENTATION, "EmotionPolicy", policy)
    stack.register(OsiLayer.PRESENTATION, "GyroCalibrator", calibrator)
    stack.register(OsiLayer.APPLICATION, "RobotMainWindow", window)

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
        calibrator=calibrator,
        bridge=bridge,
        gimbal_controller=gimbal_controller,
    )
    stack.register(
        OsiLayer.SESSION,
        "RobotRuntime",
        runtime,
        description="Qt polling loop",
    )
    app.aboutToQuit.connect(runtime.stop)
    app.aboutToQuit.connect(video_stream.stop)

    LOGGER.info("%s", describe_stack(stack))

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
