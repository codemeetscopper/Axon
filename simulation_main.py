from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtWidgets import QApplication

from axon_ros.osi import OsiLayer, OsiStack, describe_stack
from axon_ros.ui import SimulatorMainWindow
from axon_ui import apply_dark_palette
from robot_control import EmotionPolicy, GyroCalibrator

LOGGER = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Axon simulator")
    parser.add_argument(
        "--bridge-host",
        default=None,
        help="Default TCP bridge host shown in the Robot Link tab",
    )
    parser.add_argument(
        "--bridge-port",
        type=int,
        default=None,
        help="Default TCP bridge port shown in the Robot Link tab",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    policy = EmotionPolicy()
    calibrator = GyroCalibrator()
    stack = OsiStack("Simulator")
    stack.register(OsiLayer.PRESENTATION, "EmotionPolicy", policy)
    stack.register(OsiLayer.PRESENTATION, "GyroCalibrator", calibrator)

    window = SimulatorMainWindow(
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
        policy=policy,
        calibrator=calibrator,
    )
    stack.register(OsiLayer.APPLICATION, "SimulatorMainWindow", window)
    LOGGER.debug("%s", describe_stack(stack))
    window.resize(1220, 620)
    window.show()
    app.aboutToQuit.connect(window.shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
