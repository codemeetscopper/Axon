from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from axon_ros.ui import SimulatorMainWindow
from axon_ui import apply_dark_palette
from robot_control.remote_bridge import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Axon simulator with optional remote connection",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_BRIDGE_HOST,
        help="Robot bridge hostname or IP",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_BRIDGE_PORT,
        help="Robot bridge TCP port",
    )
    parser.add_argument(
        "--connect",
        action="store_true",
        help="Connect to the robot as soon as the UI launches",
    )
    args = parser.parse_args(argv if argv is not None else None)

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    window = SimulatorMainWindow(
        default_host=args.host,
        default_port=args.port,
        auto_connect=args.connect,
    )
    window.resize(1220, 620)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
