from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from axon_ros.osi import OsiLayer, OsiStack, describe_stack
from axon_ros.runtime import RobotMainWindow
from axon_ui import InfoPanel, RoboticFaceWidget, TelemetryPanel, apply_dark_palette
from robot_control.remote_bridge import RemoteBridgeController

DEFAULT_HOST = "192.168.1.169"
DEFAULT_PORT = 8765

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remote Axon UI client")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Robot IP address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Serial bridge port")
    args = parser.parse_args(argv if argv is not None else None)

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Remote UI")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    face = RoboticFaceWidget()
    telemetry = TelemetryPanel()
    info_panel = InfoPanel()
    info_panel.set_manual_entries(ip=f"Robot: {args.host}", wifi="Serial bridge")
    window = RobotMainWindow(face, (info_panel, telemetry))

    controller = RemoteBridgeController(face, telemetry)
    controller.connect_to(args.host, args.port)

    stack = OsiStack("Remote UI")
    stack.register(OsiLayer.NETWORK, "RemoteBridgeController", controller)
    stack.register(OsiLayer.APPLICATION, "RobotMainWindow", window)
    LOGGER.debug("%s", describe_stack(stack))

    app.aboutToQuit.connect(controller.disconnect)
    window.resize(1024, 600)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
