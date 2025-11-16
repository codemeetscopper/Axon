from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from axon_ros.ui import SimulatorMainWindow
from axon_ui import apply_dark_palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Robotic Face Demo")
    app.setStyle("Fusion")
    apply_dark_palette(app)

    window = SimulatorMainWindow()
    window.resize(1220, 620)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
