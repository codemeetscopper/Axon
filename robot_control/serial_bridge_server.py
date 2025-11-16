"""Expose sensor telemetry and command passthrough over TCP."""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Optional

from robot_control.sensor_data import SensorSample

from .serial_bridge_config import SerialBridgeConfig
from .serial_reader import SerialReader

LOGGER = logging.getLogger(__name__)


class SerialBridgeServer:
    """Expose the serial transport over TCP so remote tools can issue commands."""

    def __init__(
        self,
        reader: SerialReader,
        *,
        config: SerialBridgeConfig | None = None,
    ) -> None:
        self._reader = reader
        self._config = config or SerialBridgeConfig()
        self._stop_event = threading.Event()
        self._server_thread: Optional[threading.Thread] = None
        self._server_socket: Optional[socket.socket] = None
        self._client_threads: set[threading.Thread] = set()
        self._client_sockets: set[socket.socket] = set()
        self._clients_lock = threading.Lock()
        self._reader.add_line_consumer(self.publish_serial_line)

    def start(self) -> None:
        if self._server_thread and self._server_thread.is_alive():
            return
        self._stop_event.clear()
        self._server_thread = threading.Thread(
            target=self._serve,
            name="SerialBridgeServer",
            daemon=True,
        )
        self._server_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                LOGGER.debug("Failed to close serial bridge socket cleanly")
        with self._clients_lock:
            for conn in list(self._client_sockets):
                try:
                    conn.close()
                except OSError:
                    pass
            self._client_sockets.clear()
        for thread in list(self._client_threads):
            thread.join(timeout=0.5)
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
        self._server_thread = None
        self._server_socket = None
        self._client_threads.clear()

    def publish_sample(self, sample: SensorSample) -> None:
        payload = json.dumps(sample.as_dict())
        frame = f"telemetry {payload}\n".encode(self._config.encoding)
        self._broadcast(frame)

    def publish_serial_line(self, line: str) -> None:
        """Forward a raw serial line to every connected client."""

        frame = f"{line}\n".encode(self._config.encoding, errors="ignore")
        self._broadcast(frame)

    def _serve(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._config.host, self._config.port))
        sock.listen()
        sock.settimeout(1.0)
        self._server_socket = sock
        LOGGER.info(
            "Serial bridge listening on %s:%s",
            self._config.host,
            self._config.port,
        )
        try:
            while not self._stop_event.is_set():
                try:
                    client, address = sock.accept()
                except socket.timeout:
                    continue
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, address),
                    name=f"SerialBridgeClient-{address[0]}:{address[1]}",
                    daemon=True,
                )
                self._client_threads.add(thread)
                thread.start()
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _handle_client(self, conn: socket.socket, address: tuple[str, int]) -> None:
        LOGGER.info("Client connected from %s:%s", *address)
        buffer = b""
        try:
            conn.sendall(self._config.welcome_message.encode(self._config.encoding))
            conn.settimeout(1.0)
            self._register_client(conn)
            while not self._stop_event.is_set():
                try:
                    chunk = conn.recv(1024)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._process_command(conn, line)
        except OSError as exc:
            LOGGER.debug("Client %s:%s disconnected: %s", address[0], address[1], exc)
        finally:
            self._drop_client(conn)
            LOGGER.info("Client disconnected from %s:%s", *address)
            self._client_threads.discard(threading.current_thread())

    def _register_client(self, conn: socket.socket) -> None:
        with self._clients_lock:
            self._client_sockets.add(conn)

    def _drop_client(self, conn: socket.socket) -> None:
        with self._clients_lock:
            if conn in self._client_sockets:
                self._client_sockets.remove(conn)
        try:
            conn.close()
        except OSError:
            pass

    def _broadcast(self, frame: bytes) -> None:
        with self._clients_lock:
            clients = list(self._client_sockets)
        for conn in clients:
            try:
                conn.sendall(frame)
            except OSError:
                self._drop_client(conn)

    def _process_command(self, conn: socket.socket, payload: bytes) -> None:
        command = payload.decode(self._config.encoding, errors="ignore").strip()
        if not command:
            return
        try:
            self._reader.send_command(command)
            response = f"echo: {command}\n".encode(self._config.encoding)
        except Exception as exc:
            response = f"error: {exc}\n".encode(self._config.encoding)
        try:
            conn.sendall(response)
        except OSError:
            self._drop_client(conn)
