"""Expose a TCP socket that forwards commands to the robot's serial port."""

from __future__ import annotations

import json
import logging
import socket
import threading
from dataclasses import dataclass
from typing import Optional

from .sensor_data import SensorSample
from .serial_reader import SerialReader

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SerialCommandServerConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    welcome_message: str = "Axon serial bridge ready\n"
    encoding: str = "utf-8"


class SerialCommandServer:
    """Expose the serial transport over TCP so remote tools can issue commands."""

    def __init__(
        self,
        reader: SerialReader,
        *,
        config: SerialCommandServerConfig | None = None,
    ) -> None:
        self._reader = reader
        self._config = config or SerialCommandServerConfig()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._clients: set[threading.Thread] = set()
        self._client_sockets: set[socket.socket] = set()
        self._client_lock = threading.Lock()
        self._listener_registered = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, name="SerialCommandServer", daemon=True)
        self._thread.start()
        if not self._listener_registered:
            self._reader.add_listener(self._handle_sample)
            self._listener_registered = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                LOGGER.debug("Failed to close command socket cleanly")
        for thread in list(self._clients):
            thread.join(timeout=0.5)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._socket = None
        self._clients.clear()
        with self._client_lock:
            for conn in list(self._client_sockets):
                try:
                    conn.close()
                except OSError:
                    pass
            self._client_sockets.clear()
        if self._listener_registered:
            self._reader.remove_listener(self._handle_sample)
            self._listener_registered = False

    def _serve(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._config.host, self._config.port))
        sock.listen()
        sock.settimeout(1.0)
        self._socket = sock
        LOGGER.info(
            "Serial command server listening on %s:%s",
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
                    name=f"SerialCommandClient-{address[0]}:{address[1]}",
                    daemon=True,
                )
                self._clients.add(thread)
                thread.start()
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _handle_client(self, conn: socket.socket, address: tuple[str, int]) -> None:
        LOGGER.info("Client connected from %s:%s", *address)
        buffer = b""
        with self._client_lock:
            self._client_sockets.add(conn)
        try:
            conn.sendall(self._config.welcome_message.encode(self._config.encoding))
            conn.settimeout(1.0)
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
            try:
                conn.close()
            except OSError:
                pass
            LOGGER.info("Client disconnected from %s:%s", *address)
            self._clients.discard(threading.current_thread())
            with self._client_lock:
                self._client_sockets.discard(conn)

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
            pass

    def _handle_sample(self, sample: SensorSample, raw_payload: str) -> None:
        try:
            data = sample.as_dict()
            data["raw"] = raw_payload
            payload = json.dumps(data, separators=(",", ":"))
        except Exception:
            LOGGER.debug("Failed to encode telemetry for broadcast", exc_info=True)
            return
        self._broadcast(f"telemetry {payload}\n")

    def _broadcast(self, message: str) -> None:
        data = message.encode(self._config.encoding, errors="ignore")
        with self._client_lock:
            sockets = list(self._client_sockets)
        for conn in sockets:
            try:
                conn.sendall(data)
            except OSError:
                with self._client_lock:
                    self._client_sockets.discard(conn)
