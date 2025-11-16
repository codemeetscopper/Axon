"""Utilities for streaming telemetry from the TCP bridge into the face widget."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QAbstractSocket

from axon_ui import RoboticFaceWidget, TelemetryPanel
from axon_ui.bridge_client import SerialBridgeConnection

from .emotion_policy import EmotionPolicy
from .face_controller import FaceController
from .sensor_data import SensorSample

DEFAULT_BRIDGE_HOST = "192.168.1.169"
DEFAULT_BRIDGE_PORT = 8765


class RemoteBridgeController(QObject):
    """Bridge telemetry from the TCP server to the Qt face widget."""

    connectionStateChanged = Signal(QAbstractSocket.SocketState)
    remoteActiveChanged = Signal(bool)
    telemetryReceived = Signal(SensorSample)
    lineReceived = Signal(str)
    errorOccurred = Signal(str)

    def __init__(
        self,
        face: RoboticFaceWidget,
        telemetry_panel: TelemetryPanel,
        *,
        policy: Optional[EmotionPolicy] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._telemetry_panel = telemetry_panel
        self._connection = SerialBridgeConnection(self)
        self._connection.stateChanged.connect(self._handle_state_changed)
        self._connection.telemetryReceived.connect(self._handle_telemetry)
        self._connection.lineReceived.connect(self.lineReceived)
        self._connection.errorOccurred.connect(self.errorOccurred)
        self._face_controller = FaceController(face, policy or EmotionPolicy(), parent=self)
        self._connected = False

    # ------------------------------------------------------------------
    # Connection control
    # ------------------------------------------------------------------
    def connect_to(self, host: str = DEFAULT_BRIDGE_HOST, port: int = DEFAULT_BRIDGE_PORT) -> None:
        self._connection.connect_to(host, port)

    def disconnect(self) -> None:
        self._connection.disconnect()

    def send_command(self, command: str) -> None:
        self._connection.send_command(command)

    def is_connected(self) -> bool:
        return self._connection.is_connected()

    def state(self) -> QAbstractSocket.SocketState:
        return self._connection.state()

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------
    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:
        was_connected = self._connected
        self._connected = state == QAbstractSocket.SocketState.ConnectedState
        if was_connected != self._connected:
            self.remoteActiveChanged.emit(self._connected)
            if not self._connected:
                self._telemetry_panel.set_streaming(False)
        self.connectionStateChanged.emit(state)

    def _handle_telemetry(self, payload: dict[str, object]) -> None:
        try:
            sample = SensorSample.from_dict(payload)
        except (KeyError, ValueError, TypeError):
            self.errorOccurred.emit("Received malformed telemetry frame")
            return

        self._telemetry_panel.update_sample(sample)
        self._face_controller.apply_sample(sample)
        self.telemetryReceived.emit(sample)
