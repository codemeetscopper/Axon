from __future__ import annotations

import json
import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6 import QtCore, QtWidgets


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("serial-mock")


@dataclass
class MockState:
    speed_left: float = 0.0
    speed_right: float = 0.0
    pwm_left: int = 0
    pwm_right: int = 0
    oled_lines: Dict[int, str] = field(default_factory=dict)
    feedback_enabled: bool = False
    echo_enabled: bool = False


class ClientConnection:
    def __init__(self, sock: socket.socket, addr: tuple[str, int]):
        self.sock = sock
        self.addr = addr
        self.outbound: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._send_thread.start()

    def enqueue(self, line: str) -> None:
        self.outbound.put(line)

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()

    def _send_loop(self) -> None:
        while not self._stop.is_set():
            try:
                line = self.outbound.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.sock.sendall(f"{line}\n".encode("utf-8"))
            except OSError:
                break


class MockChassisServer:
    def __init__(self, host: str, port: int, state: MockState):
        self.host = host
        self.port = port
        self.state = state
        self._server: Optional[socket.socket] = None
        self._clients: List[ClientConnection] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Mock server listening on %s:%s", self.host, self.port)

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            try:
                self._server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._server.close()
        with self._lock:
            for client in list(self._clients):
                client.close()
            self._clients.clear()

    def broadcast(self, payload: Dict) -> None:
        line = json.dumps(payload, separators=(",", ":"))
        with self._lock:
            for client in list(self._clients):
                client.enqueue(line)

    def _run(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._server.settimeout(1.0)
        while not self._stop.is_set():
            try:
                client_sock, addr = self._server.accept()
            except socket.timeout:
                continue
            client = ClientConnection(client_sock, addr)
            with self._lock:
                self._clients.append(client)
            threading.Thread(target=self._client_loop, args=(client,), daemon=True).start()
            logger.info("Client connected: %s", addr)

    def _client_loop(self, client: ClientConnection) -> None:
        try:
            fileobj = client.sock.makefile("r")
            for line in fileobj:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from %s: %s", client.addr, line)
                    continue
                self._handle_command(obj, client)
        except OSError:
            pass
        finally:
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
            client.close()
            logger.info("Client disconnected: %s", client.addr)

    def _handle_command(self, obj: Dict, client: ClientConnection) -> None:
        if self.state.echo_enabled:
            client.enqueue(json.dumps(obj))

        cmd_type = obj.get("T")
        if cmd_type == 1:
            self.state.speed_left = float(obj.get("L", 0.0))
            self.state.speed_right = float(obj.get("R", 0.0))
        elif cmd_type == 11:
            self.state.pwm_left = int(obj.get("L", 0))
            self.state.pwm_right = int(obj.get("R", 0))
        elif cmd_type == 3:
            line_num = int(obj.get("lineNum", 0))
            text = str(obj.get("Text", ""))
            self.state.oled_lines[line_num] = text
        elif cmd_type == -3:
            self.state.oled_lines.clear()
        elif cmd_type == 130:
            client.enqueue(json.dumps(self._feedback_payload()))
        elif cmd_type == 131:
            self.state.feedback_enabled = bool(obj.get("cmd", 0))
        elif cmd_type == 143:
            self.state.echo_enabled = bool(obj.get("cmd", 0))

    def _feedback_payload(self) -> Dict:
        return {
            "T": 130,
            "ts": time.time(),
            "L": self.state.speed_left,
            "R": self.state.speed_right,
            "pwmL": self.state.pwm_left,
            "pwmR": self.state.pwm_right,
            "battery": 12.3,
            "imu": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "oled": self.state.oled_lines,
        }


class MainWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wave Rover Serial Mock")
        self.state = MockState()
        self.server: Optional[MockChassisServer] = None

        self.host_input = QtWidgets.QLineEdit("127.0.0.1")
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(7000)

        self.interval_input = QtWidgets.QDoubleSpinBox()
        self.interval_input.setRange(0.05, 10.0)
        self.interval_input.setValue(0.2)
        self.interval_input.setSingleStep(0.05)

        self.feedback_checkbox = QtWidgets.QCheckBox("Continuous feedback enabled")
        self.echo_checkbox = QtWidgets.QCheckBox("Echo commands")

        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)

        layout = QtWidgets.QFormLayout()
        layout.addRow("Host", self.host_input)
        layout.addRow("Port", self.port_input)
        layout.addRow("Feedback interval (s)", self.interval_input)
        layout.addRow(self.feedback_checkbox)
        layout.addRow(self.echo_checkbox)
        layout.addRow(self.start_button, self.stop_button)
        layout.addRow("Log", self.log)
        self.setLayout(layout)

        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.feedback_checkbox.toggled.connect(self._toggle_feedback)
        self.echo_checkbox.toggled.connect(self._toggle_echo)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._publish_feedback)

    def log_message(self, message: str) -> None:
        self.log.appendPlainText(message)

    def start_server(self) -> None:
        host = self.host_input.text().strip()
        port = int(self.port_input.value())
        self.server = MockChassisServer(host, port, self.state)
        self.server.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.timer.start(int(self.interval_input.value() * 1000))
        self.log_message(f"Server started on {host}:{port}")

    def stop_server(self) -> None:
        if self.server:
            self.server.stop()
            self.server = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.timer.stop()
        self.log_message("Server stopped")

    def closeEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        self.stop_server()
        event.accept()

    def _publish_feedback(self) -> None:
        if not self.server or not self.state.feedback_enabled:
            return
        payload = self.server._feedback_payload()
        self.server.broadcast(payload)
        self.log_message(f"Feedback: {payload}")

    def _toggle_feedback(self, checked: bool) -> None:
        self.state.feedback_enabled = checked

    def _toggle_echo(self, checked: bool) -> None:
        self.state.echo_enabled = checked


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.resize(520, 480)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
