from __future__ import annotations

import json
import struct
from typing import Optional

from PySide6.QtCore import QObject, QBuffer, QIODevice, Slot
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket


class VideoStreamServer(QObject):
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8770,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._host = host
        self._port = port
        self._server = QTcpServer(self)
        self._server.newConnection.connect(self._handle_connection)
        self._clients: dict[QTcpSocket, bytearray] = {}
        self._quality = 70

        self._camera = None
        self._capture_session = None
        self._video_sink = None

    def start(self) -> bool:
        if self._server.isListening():
            return True
        if self._camera is None:
            from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QVideoSink

            self._camera = QCamera()
            self._capture_session = QMediaCaptureSession()
            self._video_sink = QVideoSink()
            self._capture_session.setCamera(self._camera)
            self._capture_session.setVideoSink(self._video_sink)
            self._video_sink.videoFrameChanged.connect(self._on_frame)
        started = self._server.listen(QHostAddress(self._host), self._port)
        if started:
            self._camera.start()
        return started

    def stop(self) -> None:
        if self._server.isListening():
            self._server.close()
        for client in list(self._clients.keys()):
            client.disconnectFromHost()
            client.close()
        self._clients.clear()
        if self._camera is not None:
            self._camera.stop()

    @Slot()
    def _handle_connection(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                break
            client.readyRead.connect(lambda c=client: self._handle_ready_read(c))
            client.disconnected.connect(lambda c=client: self._drop_client(c))
            client.setSocketOption(QAbstractSocket.SocketOption.LowDelayOption, 1)
            self._clients[client] = bytearray()

    def _drop_client(self, client: QTcpSocket) -> None:
        if client in self._clients:
            self._clients.pop(client, None)
        client.close()

    def _handle_ready_read(self, client: QTcpSocket) -> None:
        buffer = self._clients.get(client)
        if buffer is None:
            return
        buffer.extend(client.readAll().data())
        while len(buffer) >= 8:
            message_type = bytes(buffer[:4])
            length = struct.unpack("!I", buffer[4:8])[0]
            if len(buffer) < 8 + length:
                break
            payload = bytes(buffer[8 : 8 + length])
            del buffer[: 8 + length]
            if message_type == b"CTRL":
                self._apply_control(payload)

    def _apply_control(self, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return
        quality = data.get("quality")
        if isinstance(quality, int):
            self._quality = max(10, min(95, quality))

    @Slot()
    def _on_frame(self, frame) -> None:
        if not self._clients:
            return
        image = frame.toImage()
        if image.isNull():
            return
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "JPEG", self._quality)
        payload = bytes(buffer.data())
        header = b"FRAM" + struct.pack("!I", len(payload))
        data = header + payload
        for client in list(self._clients.keys()):
            if client.state() != QAbstractSocket.SocketState.ConnectedState:
                self._drop_client(client)
                continue
            client.write(data)
