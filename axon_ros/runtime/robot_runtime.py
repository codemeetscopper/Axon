"""Qt-aware runtime loop that keeps the face in sync with live telemetry."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QTimer

from robot_control import FaceController, SerialReader
from robot_control.gyro_calibrator import GyroCalibrator
from robot_control.serial_bridge_server import SerialBridgeServer
from axon_ui import TelemetryPanel


class RobotRuntime(QObject):
    """Manage the serial polling loop inside the Qt event loop."""

    def __init__(
        self,
        reader: SerialReader,
        controller: FaceController,
        telemetry: TelemetryPanel,
        poll_interval_ms: int = 40,
        calibrator: GyroCalibrator | None = None,
        bridge: SerialBridgeServer | None = None,
        parent: Optional[QObject] = None,
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
        self._bridge = bridge

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._reader.start()
        if self._bridge is not None:
            self._bridge.start()
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            self._reader.stop()
            if self._bridge is not None:
                self._bridge.stop()
            return
        self._running = False
        self._timer.stop()
        self._reader.stop()
        if self._bridge is not None:
            self._bridge.stop()

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
        if self._bridge is not None:
            self._bridge.publish_sample(sample)
