import json
import sys
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class RobotTcpClient(QObject):
    connection_changed = Signal(bool)
    message_received = Signal(str)
    error_message = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._socket = QTcpSocket(self)
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.errorOccurred.connect(self._on_error)

        self._buffer = ""

    @Slot()
    def _on_connected(self):
        self.connection_changed.emit(True)

    @Slot()
    def _on_disconnected(self):
        self.connection_changed.emit(False)

    @Slot()
    def _on_ready_read(self):
        data = self._socket.readAll().data().decode(errors="replace")
        self._buffer += data

        # Assume newline-delimited responses
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self.message_received.emit(line)

    @Slot(QAbstractSocket.SocketError)
    def _on_error(self, socket_error):
        msg = self._socket.errorString()
        self.error_message.emit(msg)
        self.connection_changed.emit(False)

    def connect_to_host(self, host: str, port: int):
        if self._socket.state() in (
            QAbstractSocket.ConnectingState,
            QAbstractSocket.HostLookupState,
        ):
            return
        if self._socket.state() == QAbstractSocket.ConnectedState:
            self._socket.disconnectFromHost()
        self._socket.connectToHost(host, port)

    def is_connected(self) -> bool:
        return self._socket.state() == QAbstractSocket.ConnectedState

    def send_text(self, text: str):
        if not self.is_connected():
            self.error_message.emit("Not connected")
            return
        if not text.endswith("\n"):
            text += "\n"
        self._socket.write(text.encode("utf-8"))

    def send_json(self, payload: dict):
        try:
            text = json.dumps(payload)
        except TypeError as e:
            self.error_message.emit(f"JSON error: {e}")
            return
        self.send_text(text)


class RobotControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wave Rover TCP Control")
        self.resize(1000, 700)

        self.client = RobotTcpClient(self)
        self.client.connection_changed.connect(self.on_connection_changed)
        self.client.message_received.connect(self.on_message_received)
        self.client.error_message.connect(self.on_error_message)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Connection bar ---
        conn_bar = QHBoxLayout()
        conn_bar.setSpacing(8)

        self.host_edit = QLineEdit("192.168.1.169")
        self.port_edit = QLineEdit("8765")
        self.port_edit.setFixedWidth(80)
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        self.connect_button = QPushButton("Connect")

        conn_bar.addWidget(QLabel("Host:"))
        conn_bar.addWidget(self.host_edit)
        conn_bar.addWidget(QLabel("Port:"))
        conn_bar.addWidget(self.port_edit)
        conn_bar.addWidget(self.connect_button)
        conn_bar.addStretch()
        conn_bar.addWidget(self.status_label)

        main_layout.addLayout(conn_bar)

        self.connect_button.clicked.connect(self.handle_connect_clicked)

        # --- Main content: left (controls) / right (log) ---
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)
        main_layout.addLayout(content_layout, 1)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        content_layout.addLayout(left_col, 2)

        right_col = QVBoxLayout()
        content_layout.addLayout(right_col, 1)

        # Movement group (speed + presets)
        left_col.addWidget(self._build_movement_group())

        # Advanced groups (PWM, OLED, Info, IO)
        advanced_row = QHBoxLayout()
        advanced_row.setSpacing(10)
        left_col.addLayout(advanced_row)

        advanced_row.addWidget(self._build_pwm_group())
        advanced_row.addWidget(self._build_oled_group())

        info_io_row = QHBoxLayout()
        info_io_row.setSpacing(10)
        left_col.addLayout(info_io_row)
        info_io_row.addWidget(self._build_info_group())
        info_io_row.addWidget(self._build_io_group())

        # Raw JSON sender
        left_col.addWidget(self._build_raw_group())

        # --- Log on right side ---
        log_group = QGroupBox("TCP / JSON Log")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        right_col.addWidget(log_group)

        # Slight dark-ish feel
        self._apply_basic_style()

    # ----------------- UI building helpers -----------------

    def _build_movement_group(self) -> QGroupBox:
        box = QGroupBox("Chassis Movement (CMD_SPEED_CTRL T=1)")
        layout = QVBoxLayout(box)

        sliders_layout = QGridLayout()
        sliders_layout.setHorizontalSpacing(10)
        sliders_layout.setVerticalSpacing(4)

        self.left_speed_slider = QSlider(Qt.Horizontal)
        self.left_speed_slider.setRange(-50, 50)
        self.left_speed_slider.setValue(0)
        self.right_speed_slider = QSlider(Qt.Horizontal)
        self.right_speed_slider.setRange(-50, 50)
        self.right_speed_slider.setValue(0)

        self.left_speed_label = QLabel("L: 0.00")
        self.right_speed_label = QLabel("R: 0.00")

        sliders_layout.addWidget(QLabel("Left speed (-0.5 .. 0.5)"), 0, 0)
        sliders_layout.addWidget(self.left_speed_slider, 0, 1)
        sliders_layout.addWidget(self.left_speed_label, 0, 2)

        sliders_layout.addWidget(QLabel("Right speed (-0.5 .. 0.5)"), 1, 0)
        sliders_layout.addWidget(self.right_speed_slider, 1, 1)
        sliders_layout.addWidget(self.right_speed_label, 1, 2)

        layout.addLayout(sliders_layout)

        self.left_speed_slider.valueChanged.connect(self.update_speed_labels)
        self.right_speed_slider.valueChanged.connect(self.update_speed_labels)

        # Preset buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_forward = QPushButton("Forward")
        self.btn_backward = QPushButton("Backward")
        self.btn_turn_left = QPushButton("Turn Left")
        self.btn_turn_right = QPushButton("Turn Right")
        self.btn_stop = QPushButton("Stop")

        btn_row.addWidget(self.btn_forward)
        btn_row.addWidget(self.btn_backward)
        btn_row.addWidget(self.btn_turn_left)
        btn_row.addWidget(self.btn_turn_right)
        btn_row.addWidget(self.btn_stop)

        layout.addLayout(btn_row)

        self.btn_forward.clicked.connect(lambda: self.send_speed(0.3, 0.3))
        self.btn_backward.clicked.connect(lambda: self.send_speed(-0.3, -0.3))
        self.btn_turn_left.clicked.connect(lambda: self.send_speed(-0.2, 0.2))
        self.btn_turn_right.clicked.connect(lambda: self.send_speed(0.2, -0.2))
        self.btn_stop.clicked.connect(lambda: self.send_speed(0.0, 0.0))

        # Apply from sliders
        apply_row = QHBoxLayout()
        self.btn_apply_slider = QPushButton("Send from sliders")
        apply_row.addStretch()
        apply_row.addWidget(self.btn_apply_slider)
        layout.addLayout(apply_row)

        self.btn_apply_slider.clicked.connect(self.send_from_sliders)

        self.update_speed_labels()
        return box

    def _build_pwm_group(self) -> QGroupBox:
        box = QGroupBox("PWM Control (CMD_PWM_INPUT T=11)")
        layout = QFormLayout(box)

        self.pwm_left_spin = QSpinBox()
        self.pwm_left_spin.setRange(-255, 255)
        self.pwm_left_spin.setValue(0)

        self.pwm_right_spin = QSpinBox()
        self.pwm_right_spin.setRange(-255, 255)
        self.pwm_right_spin.setValue(0)

        layout.addRow("Left PWM:", self.pwm_left_spin)
        layout.addRow("Right PWM:", self.pwm_right_spin)

        btn = QPushButton("Send PWM")
        btn.clicked.connect(self.send_pwm_command)
        layout.addRow(btn)
        return box

    def _build_oled_group(self) -> QGroupBox:
        box = QGroupBox("OLED Screen Control (T=3 / T=-3)")
        layout = QFormLayout(box)

        self.oled_line_spin = QSpinBox()
        self.oled_line_spin.setRange(0, 3)
        self.oled_line_spin.setValue(0)

        self.oled_text_edit = QLineEdit()
        self.oled_text_edit.setPlaceholderText("Text to display on OLED line")

        layout.addRow("Line (0-3):", self.oled_line_spin)
        layout.addRow("Text:", self.oled_text_edit)

        btn_row = QHBoxLayout()
        self.oled_send_btn = QPushButton("Send OLED Text (T=3)")
        self.oled_restore_btn = QPushButton("Restore OLED (T=-3)")

        btn_row.addWidget(self.oled_send_btn)
        btn_row.addWidget(self.oled_restore_btn)

        layout.addRow(btn_row)

        self.oled_send_btn.clicked.connect(self.send_oled_text)
        self.oled_restore_btn.clicked.connect(self.restore_oled)

        return box

    def _build_info_group(self) -> QGroupBox:
        box = QGroupBox("Info / Feedback")
        layout = QVBoxLayout(box)

        self.btn_get_imu = QPushButton("Get IMU (T=126)")
        self.btn_get_base = QPushButton("Get Base Feedback (T=130)")

        self.chk_cont_feedback = QCheckBox("Continuous Feedback (T=131)")
        self.chk_serial_echo = QCheckBox("Serial Echo (T=143)")

        layout.addWidget(self.btn_get_imu)
        layout.addWidget(self.btn_get_base)
        layout.addSpacing(6)
        layout.addWidget(self.chk_cont_feedback)
        layout.addWidget(self.chk_serial_echo)
        layout.addStretch()

        self.btn_get_imu.clicked.connect(
            lambda: self.send_json({"T": 126})
        )
        self.btn_get_base.clicked.connect(
            lambda: self.send_json({"T": 130})
        )

        self.chk_cont_feedback.toggled.connect(self.toggle_continuous_feedback)
        self.chk_serial_echo.toggled.connect(self.toggle_serial_echo)

        return box

    def _build_io_group(self) -> QGroupBox:
        box = QGroupBox("IO4 / IO5 Control (T=132)")
        layout = QFormLayout(box)

        self.io4_spin = QSpinBox()
        self.io4_spin.setRange(0, 255)
        self.io4_spin.setValue(0)

        self.io5_spin = QSpinBox()
        self.io5_spin.setRange(0, 255)
        self.io5_spin.setValue(0)

        layout.addRow("IO4 PWM:", self.io4_spin)
        layout.addRow("IO5 PWM:", self.io5_spin)

        btn = QPushButton("Send IO PWM")
        btn.clicked.connect(self.send_io_pwm)
        layout.addRow(btn)

        return box

    def _build_raw_group(self) -> QGroupBox:
        box = QGroupBox("Raw JSON Command")
        layout = QHBoxLayout(box)

        self.raw_edit = QLineEdit()
        self.raw_edit.setPlaceholderText('Example: {"T":1,"L":0.5,"R":0.5}')
        self.raw_send_btn = QPushButton("Send")

        layout.addWidget(self.raw_edit, 1)
        layout.addWidget(self.raw_send_btn)

        self.raw_send_btn.clicked.connect(self.send_raw_json)
        return box

    def _apply_basic_style(self):
        # Simple darkish log, rest default to keep it portable
        self.log_view.setStyleSheet(
            "QTextEdit { background-color: #111; color: #EEE; font-family: Consolas, monospace; }"
        )

    # ----------------- Slots / logic -----------------

    @Slot()
    def handle_connect_clicked(self):
        host = self.host_edit.text().strip()
        try:
            port = int(self.port_edit.text())
        except ValueError:
            self.append_log("[ERROR] Invalid port")
            return
        self.append_log(f"[INFO] Connecting to {host}:{port} ...")
        self.client.connect_to_host(host, port)

    @Slot(bool)
    def on_connection_changed(self, connected: bool):
        if connected:
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: #00AA00; font-weight: bold;")
            self.connect_button.setText("Reconnect")
            self.append_log("[INFO] Connected")
        else:
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.append_log("[INFO] Disconnected")

    @Slot(str)
    def on_message_received(self, msg: str):
        self.append_log(f"[RX] {msg}")

    @Slot(str)
    def on_error_message(self, msg: str):
        self.append_log(f"[ERROR] {msg}")

    def append_log(self, text: str):
        self.log_view.append(text)

    # ---- Movement ----

    @Slot()
    def update_speed_labels(self):
        l = self.left_speed_slider.value() / 100.0
        r = self.right_speed_slider.value() / 100.0
        self.left_speed_label.setText(f"L: {l:+.2f}")
        self.right_speed_label.setText(f"R: {r:+.2f}")

    def send_speed(self, left: float, right: float):
        payload = {"T": 1, "L": left, "R": right}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    @Slot()
    def send_from_sliders(self):
        l = self.left_speed_slider.value() / 100.0
        r = self.right_speed_slider.value() / 100.0
        self.send_speed(l, r)

    # ---- PWM ----

    @Slot()
    def send_pwm_command(self):
        l = self.pwm_left_spin.value()
        r = self.pwm_right_spin.value()
        payload = {"T": 11, "L": l, "R": r}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    # ---- OLED ----

    @Slot()
    def send_oled_text(self):
        line = self.oled_line_spin.value()
        text = self.oled_text_edit.text()
        payload = {"T": 3, "lineNum": line, "Text": text}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    @Slot()
    def restore_oled(self):
        payload = {"T": -3}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    # ---- Info / Feedback ----

    @Slot(bool)
    def toggle_continuous_feedback(self, checked: bool):
        cmd = 1 if checked else 0
        payload = {"T": 131, "cmd": cmd}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    @Slot(bool)
    def toggle_serial_echo(self, checked: bool):
        cmd = 1 if checked else 0
        payload = {"T": 143, "cmd": cmd}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    # ---- IO ----

    @Slot()
    def send_io_pwm(self):
        io4 = self.io4_spin.value()
        io5 = self.io5_spin.value()
        payload = {"T": 132, "IO4": io4, "IO5": io5}
        self.append_log(f"[TX] {payload}")
        self.client.send_json(payload)

    # ---- Raw ----

    @Slot()
    def send_raw_json(self):
        text = self.raw_edit.text().strip()
        if not text:
            return
        self.append_log(f"[TX RAW] {text}")
        self.client.send_text(text)

    def send_json(self, data):
        self.append_log(f"[TX RAW] {data}")
        self.client.send_text(str(data))


def main():
    app = QApplication(sys.argv)
    win = RobotControlWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
