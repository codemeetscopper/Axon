"""Reusable TCP client that talks to the serial bridge server."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket


class SerialBridgeConnection(QObject):
    """Minimal client for the TCP serial bridge exposed by the robot."""

    telemetryReceived = Signal(dict)
    lineReceived = Signal(str)
    stateChanged = Signal(QAbstractSocket.SocketState)
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket = QTcpSocket(self)
        self._socket.readyRead.connect(self._handle_ready_read)
        self._socket.errorOccurred.connect(self._handle_error)
        self._socket.stateChanged.connect(self._handle_state_changed)
        self._buffer = ""

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def connect_to(self, host: str, port: int) -> None:
        """Connect to the bridge server at *host*:*port*."""

        if not host:
            host = "127.0.0.1"
        if self._socket.state() == QAbstractSocket.SocketState.ConnectedState:
            if (
                self._socket.peerName() == host
                and self._socket.peerPort() == port
            ):
                return
            self._socket.abort()
        self._socket.connectToHost(host, port)

    def disconnect(self) -> None:
        """Close the underlying TCP connection."""

        if self._socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._socket.abort()

    def send_command(self, command: str) -> None:
        """Send *command* to the bridge if connected."""

        if self._socket.state() != QAbstractSocket.SocketState.ConnectedState:
            raise RuntimeError("Not connected to the bridge")
        payload = command.rstrip("\n") + "\n"
        data = payload.encode("utf-8")
        self._socket.write(data)

    # ------------------------------------------------------------------
    # Socket callbacks
    # ------------------------------------------------------------------
    def _handle_state_changed(self, state: QAbstractSocket.SocketState) -> None:  # pragma: no cover - Qt callback
        self.stateChanged.emit(state)

    def _handle_error(self, error: QAbstractSocket.SocketError) -> None:  # pragma: no cover - Qt callback
        if error == QAbstractSocket.SocketError.RemoteHostClosedError:
            # Remote closures are already surfaced through stateChanged.
            return
        self.errorOccurred.emit(self._socket.errorString())

    def _handle_ready_read(self) -> None:  # pragma: no cover - Qt callback
        data = bytes(self._socket.readAll()).decode("utf-8", errors="ignore")
        if not data:
            return
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._process_line(line.strip())

    def _process_line(self, line: str) -> None:
        if not line:
            return
        if line.startswith("telemetry "):
            payload = line.split(" ", 1)[1]
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                self.errorOccurred.emit(f"Malformed telemetry: {payload}")
                return
            self.telemetryReceived.emit(data)
            return
        self.lineReceived.emit(line)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def state(self) -> QAbstractSocket.SocketState:
        return self._socket.state()

    def is_connected(self) -> bool:
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    def is_connecting(self) -> bool:
        return self._socket.state() == QAbstractSocket.SocketState.ConnectingState
