from __future__ import annotations

import logging
import signal
import sys
import time

from PySide6.QtWidgets import QApplication

from axon_ros.osi import OsiLayer, OsiStack, describe_stack
from axon_ros.runtime import RobotMainWindow, RobotRuntime
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel
from robot_control import EmotionPolicy, FaceController, GyroCalibrator, SerialReadWriter
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

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Runtime")
    app.setStyle("Fusion")

    if apply_palette is not None:
        apply_palette(app)

    face = RoboticFaceWidget()
    policy = EmotionPolicy()
    calibrator = GyroCalibrator()
    controller = FaceController(face, policy)
    telemetry = TelemetryPanel()
    info_panel = InfoPanel()
    window = RobotMainWindow(face, (info_panel, telemetry))
    stack.register(OsiLayer.PRESENTATION, "EmotionPolicy", policy)
    stack.register(OsiLayer.PRESENTATION, "GyroCalibrator", calibrator)
    stack.register(OsiLayer.APPLICATION, "RobotMainWindow", window)

    # --- Voice chat (optional, degrades gracefully) ---
    voice_chat = None
    try:
        from robot_control import (
            SpeechListener, ChatEngine, SpeechSynthesizer, VoiceChatController,
        )

        listener = SpeechListener()
        chat_engine = ChatEngine(serial_reader=reader)
        synthesizer = SpeechSynthesizer()
        voice_chat = VoiceChatController(
            face, controller, listener, chat_engine, synthesizer,
            chat_overlay=window.chat_overlay,
        )
        stack.register(OsiLayer.PRESENTATION, "SpeechListener", listener,
                       description="Vosk STT mic input")
        stack.register(OsiLayer.PRESENTATION, "SpeechSynthesizer", synthesizer,
                       description="espeak-ng TTS output")
        stack.register(OsiLayer.APPLICATION, "ChatEngine", chat_engine,
                       description="Claude AI chatbot")
        stack.register(OsiLayer.APPLICATION, "VoiceChatController", voice_chat,
                       description="Voice chat orchestrator")
        LOGGER.info("Voice chat initialised")
    except ImportError:
        LOGGER.warning("Voice chat dependencies not installed; voice chat disabled")
    except Exception as exc:
        LOGGER.warning("Voice chat failed to initialise: %s", exc)

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
        calibrator=calibrator,
        bridge=bridge,
    )
    stack.register(
        OsiLayer.SESSION,
        "RobotRuntime",
        runtime,
        description="Qt polling loop",
    )
    app.aboutToQuit.connect(runtime.stop)
    if voice_chat is not None:
        app.aboutToQuit.connect(voice_chat.stop)

    LOGGER.info("%s", describe_stack(stack))

    # Support clean shutdown when Ctrl+C is pressed on the console.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    runtime.start()
    if voice_chat is not None:
        voice_chat.start()
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
