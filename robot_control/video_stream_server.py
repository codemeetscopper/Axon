from __future__ import annotations

import errno
import json
import logging
import socket
import struct
import threading
import time
from typing import Optional

import cv2

LOGGER = logging.getLogger(__name__)


class VideoStreamServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8770,
        device_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._device_index = device_index
        self._width = width
        self._height = height
        self._fps = fps
        self._quality = 70

        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._clients: dict[socket.socket, bytearray] = {}
        self._clients_lock = threading.Lock()
        self._bound_port: Optional[int] = None

    @property
    def bound_port(self) -> Optional[int]:
        return self._bound_port

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            server_socket.bind((self._host, self._port))
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                LOGGER.warning("Video stream port %s in use; selecting a free port.", self._port)
                try:
                    server_socket.bind((self._host, 0))
                except OSError as bind_exc:
                    LOGGER.warning("Video stream server failed to bind: %s", bind_exc)
                    server_socket.close()
                    return False
            else:
                LOGGER.warning("Video stream server failed to bind: %s", exc)
                server_socket.close()
                return False
        server_socket.listen()
        server_socket.settimeout(0.5)
        self._server_socket = server_socket
        self._bound_port = server_socket.getsockname()[1]

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="VideoStreamServer", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
        self._bound_port = None
        with self._clients_lock:
            for client in list(self._clients.keys()):
                try:
                    client.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        capture = cv2.VideoCapture(self._device_index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._width))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._height))
        capture.set(cv2.CAP_PROP_FPS, float(self._fps))
        frame_interval = 1.0 / max(self._fps, 1)
        try:
            while not self._stop_event.is_set():
                self._accept_clients()
                self._read_controls()

                ok, frame = capture.read()
                if not ok:
                    time.sleep(0.1)
                    continue
                result, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), int(self._quality)],
                )
                if not result:
                    continue

                payload = encoded.tobytes()
                header = b"FRAM" + struct.pack("!I", len(payload))
                data = header + payload
                self._broadcast(data)
                time.sleep(frame_interval)
        finally:
            capture.release()

    def _accept_clients(self) -> None:
        if self._server_socket is None:
            return
        while not self._stop_event.is_set():
            try:
                client, _address = self._server_socket.accept()
            except socket.timeout:
                break
            except OSError:
                return
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.setblocking(False)
            with self._clients_lock:
                self._clients[client] = bytearray()

    def _read_controls(self) -> None:
        with self._clients_lock:
            clients = list(self._clients.items())
        for client, buffer in clients:
            try:
                chunk = client.recv(4096)
            except BlockingIOError:
                continue
            except OSError:
                self._drop_client(client)
                continue
            if not chunk:
                self._drop_client(client)
                continue
            buffer.extend(chunk)
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

    def _broadcast(self, data: bytes) -> None:
        with self._clients_lock:
            clients = list(self._clients.keys())
        for client in clients:
            try:
                client.sendall(data)
            except OSError:
                self._drop_client(client)

    def _drop_client(self, client: socket.socket) -> None:
        with self._clients_lock:
            if client in self._clients:
                self._clients.pop(client, None)
        try:
            client.close()
        except OSError:
            pass
