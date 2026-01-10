from __future__ import annotations

import json
import struct
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class VideoStreamClient(QObject):
    frame_received = Signal(QImage)
    connection_changed = Signal(bool)
    error_message = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._socket = QTcpSocket(self)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.errorOccurred.connect(self._on_error)
        self._buffer = bytearray()

    def connect_to_host(self, host: str, port: int) -> None:
        if self._socket.state() in (
            QAbstractSocket.SocketState.ConnectingState,
            QAbstractSocket.SocketState.HostLookupState,
        ):
            return
        if self._socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self._socket.disconnectFromHost()
        self._socket.connectToHost(host, port)
        self._socket.setSocketOption(QAbstractSocket.SocketOption.LowDelayOption, 1)

    def disconnect(self) -> None:
        if self._socket.state() == QAbstractSocket.SocketState.ConnectedState:
            self._socket.disconnectFromHost()

    def is_connected(self) -> bool:
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    def send_quality(self, quality: int) -> None:
        payload = json.dumps({"quality": int(quality)}).encode("utf-8")
        header = b"CTRL" + struct.pack("!I", len(payload))
        self._socket.write(header + payload)

    @Slot()
    def _on_connected(self) -> None:
        self.connection_changed.emit(True)

    @Slot()
    def _on_disconnected(self) -> None:
        self.connection_changed.emit(False)

    @Slot(QAbstractSocket.SocketError)
    def _on_error(self, socket_error: QAbstractSocket.SocketError) -> None:
        self.error_message.emit(self._socket.errorString())
        self.connection_changed.emit(False)

    @Slot()
    def _on_ready_read(self) -> None:
        self._buffer.extend(self._socket.readAll().data())
        while len(self._buffer) >= 8:
            message_type = bytes(self._buffer[:4])
            length = struct.unpack("!I", self._buffer[4:8])[0]
            if len(self._buffer) < 8 + length:
                break
            payload = bytes(self._buffer[8 : 8 + length])
            del self._buffer[: 8 + length]
            if message_type == b"FRAM":
                image = QImage.fromData(payload, "JPEG")
                if not image.isNull():
                    self.frame_received.emit(image)


class VideoStreamViewer(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Camera feed", parent)
        layout = QVBoxLayout(self)
        self._label = QLabel("No video")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumHeight(240)
        self._label.setStyleSheet(
            "background-color: #101010; color: #9aa0a6; border-radius: 12px;"
        )
        layout.addWidget(self._label)
        self._last_image = QImage()

    def update_frame(self, image: QImage) -> None:
        self._last_image = image
        self._render_image()

    def _render_image(self) -> None:
        if self._last_image.isNull():
            self._label.setText("No video")
            return
        scaled = self._last_image.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._label.setPixmap(QPixmap.fromImage(scaled))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_image()


class VideoStreamPanel(QWidget):
    def __init__(
        self,
        viewer: VideoStreamViewer,
        parent: Optional[QWidget] = None,
        default_host: str = "127.0.0.1",
        default_port: int = 8770,
    ) -> None:
        super().__init__(parent)
        self._viewer = viewer
        self._client = VideoStreamClient(self)
        self._client.frame_received.connect(self._viewer.update_frame)
        self._client.connection_changed.connect(self._handle_connection)
        self._client.error_message.connect(self._handle_error)
        self._default_host = default_host
        self._default_port = default_port
        self._build_ui()

    def shutdown(self) -> None:
        self._client.disconnect()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        connection_box = QGroupBox("USB camera stream")
        connection_layout = QFormLayout(connection_box)
        self._host_input = QLineEdit(self._default_host)
        self._port_input = QLineEdit(str(self._default_port))
        self._status_label = QLabel("Disconnected")
        self._status_label.setStyleSheet("color: #d65c5c; font-weight: bold;")
        self._connect_button = QPushButton("Connect")
        self._connect_button.clicked.connect(self._toggle_connection)

        connection_layout.addRow("Host", self._host_input)
        connection_layout.addRow("Port", self._port_input)
        connection_layout.addRow(self._connect_button, self._status_label)

        quality_box = QGroupBox("Quality")
        quality_layout = QHBoxLayout(quality_box)
        self._quality_slider = QSlider(Qt.Orientation.Horizontal)
        self._quality_slider.setRange(25, 95)
        self._quality_slider.setValue(70)
        self._quality_value = QLabel("70")
        self._quality_slider.valueChanged.connect(self._handle_quality_change)
        quality_layout.addWidget(QLabel("JPEG"))
        quality_layout.addWidget(self._quality_slider)
        quality_layout.addWidget(self._quality_value)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #f2c94c;")

        layout.addWidget(connection_box)
        layout.addWidget(quality_box)
        layout.addWidget(self._error_label)
        layout.addStretch()

    def _toggle_connection(self) -> None:
        if self._client.is_connected():
            self._client.disconnect()
            return
        host = self._host_input.text().strip()
        try:
            port = int(self._port_input.text().strip())
        except ValueError:
            self._error_label.setText("Invalid port.")
            return
        self._error_label.clear()
        self._client.connect_to_host(host, port)

    def _handle_quality_change(self, value: int) -> None:
        self._quality_value.setText(str(value))
        if self._client.is_connected():
            self._client.send_quality(value)

    def _handle_connection(self, connected: bool) -> None:
        if connected:
            self._status_label.setText("Connected")
            self._status_label.setStyleSheet("color: #5cb85c; font-weight: bold;")
            self._connect_button.setText("Disconnect")
            self._client.send_quality(self._quality_slider.value())
        else:
            self._status_label.setText("Disconnected")
            self._status_label.setStyleSheet("color: #d65c5c; font-weight: bold;")
            self._connect_button.setText("Connect")

    def _handle_error(self, message: str) -> None:
        self._error_label.setText(message)
