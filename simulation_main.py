from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from axon_ros.ui import SimulatorMainWindow
from axon_ui import apply_dark_palette


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

    window = SimulatorMainWindow(
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
    )
    window.resize(1220, 620)
    window.show()
    app.aboutToQuit.connect(window.shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
