from __future__ import annotations

import re
import socket
import subprocess
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from robot_control.sensor_data import SensorSample


Formatter = Callable[[float], str]


class CollapsiblePanel(QFrame):
    """Convenience base class for panels that can collapse to a toggle icon."""

    collapsedChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._collapsed = True
        self._toggle_button: Optional[QPushButton] = None
        self._content_frame: Optional[QFrame] = None
        self._shadow = None

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._apply_collapsed_state(collapsed)

    def expand(self) -> None:
        self.set_collapsed(False)

    def collapse(self) -> None:
        self.set_collapsed(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def _apply_collapsed_state(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setProperty("collapsed", "true" if collapsed else "false")
        if self.style() is not None:
            self.style().unpolish(self)
            self.style().polish(self)
        if self._content_frame is not None:
            self._content_frame.setVisible(not collapsed)
        self._on_collapse_state_changed()
        self.collapsedChanged.emit(collapsed)

    def _on_collapse_state_changed(self) -> None:
        self._apply_toggle_palette()
        self._update_toggle_icon()
        self._update_shadow()

    def _apply_toggle_palette(self) -> None:
        pass

    def _update_toggle_icon(self) -> None:
        pass

    def _update_shadow(self) -> None:
        pass


class TelemetryPanel(CollapsiblePanel):
    """Display the latest telemetry sample."""

    _FIELDS: tuple[tuple[str, str, Formatter, str], ...] = (
        ("left_speed", "left", lambda value: f"{value:.0f}", "#4CC9F0"),
        ("right_speed", "right", lambda value: f"{value:.0f}", "#4895EF"),
        ("roll", "roll", lambda value: f"{value:+.1f}°", "#4361EE"),
        ("pitch", "pitch", lambda value: f"{value:+.1f}°", "#560BAD"),
        ("yaw", "yaw", lambda value: f"{value:+.1f}°", "#B5179E"),
        ("temperature_c", "temperature", lambda value: f"{value:.1f}°C", "#F72585"),
        ("voltage_v", "voltage", lambda value: f"{value:.2f}V", "#2DD881"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value_labels: dict[str, QLabel] = {}
        self._formatters: dict[str, Formatter] = {}
        self._connection_state: str = "waiting"
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(450)
        self._blink_timer.timeout.connect(self._handle_blink)
        self._streaming = False
        self.setObjectName("telemetryPanel")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._build_ui()
        self.set_streaming(False)
        self._apply_collapsed_state(True)

    def _build_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#telemetryPanel {"
            "background-color: rgba(4, 9, 20, 0.65);"
            "border-radius: 16px;"
            "border: none;"
            "}"
            "#telemetryPanel QLabel {"
            "color: #e8f1ff;"
            "font-size: 14px;"
            "font-weight: 500;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(6)

        content = QFrame()
        content.setObjectName("telemetryContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        layout.addWidget(content, 1)
        self._content_frame = content

        self._toggle_button = QPushButton()
        self._toggle_button.setObjectName("telemetryToggle")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setMinimumSize(26, 26)
        self._toggle_button.setIconSize(QSize(20, 20))
        self._toggle_button.setToolTip("Show/Hide telemetry")
        self._toggle_button.clicked.connect(self.toggle)
        self._toggle_button.setText("")
        layout.addWidget(self._toggle_button, 0, Qt.AlignmentFlag.AlignRight)

        for index, (field, icon_key, formatter, color) in enumerate(self._FIELDS):
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            icon_pixmap = self._build_icon_pixmap(icon_key, color)
            icon_label.setPixmap(icon_pixmap)
            icon_label.setFixedSize(icon_pixmap.size())
            content_layout.addWidget(icon_label)

            value_label = QLabel("--")
            value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value_label.setStyleSheet(
                "color: #e8f1ff; font-size: 14px; font-weight: 600;"
            )
            value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            content_layout.addWidget(value_label)
            self._value_labels[field] = value_label
            self._formatters[field] = formatter

            if index < len(self._FIELDS) - 1:
                separator = QFrame()
                separator.setObjectName("telemetrySeparator")
                separator.setFixedSize(1, 14)
                separator.setStyleSheet(
                    "QFrame#telemetrySeparator {"
                    "background-color: rgba(232, 241, 255, 0.12);"
                    "border: none;"
                    "}"
                )
                content_layout.addWidget(separator)

        content_layout.addStretch(1)
        self._apply_toggle_palette()
        self._update_toggle_icon()

        self._shadow = None

    def _build_icon_pixmap(self, icon_key: str, color: str) -> QPixmap:
        size = 22
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        qcolor = QColor(color)
        pen = QPen(qcolor)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(qcolor)

        center = pixmap.rect().center()
        w = float(size)
        h = float(size)

        if icon_key == "left":
            points = QPolygonF(
                [
                    QPointF(w * 0.68, h * 0.22),
                    QPointF(w * 0.36, h * 0.50),
                    QPointF(w * 0.68, h * 0.78),
                ]
            )
            painter.drawPolygon(points)
            painter.drawLine(QPointF(w * 0.32, h * 0.50), QPointF(w * 0.84, h * 0.50))
        elif icon_key == "right":
            points = QPolygonF(
                [
                    QPointF(w * 0.32, h * 0.22),
                    QPointF(w * 0.64, h * 0.50),
                    QPointF(w * 0.32, h * 0.78),
                ]
            )
            painter.drawPolygon(points)
            painter.drawLine(QPointF(w * 0.68, h * 0.50), QPointF(w * 0.16, h * 0.50))
        elif icon_key == "roll":
            radius = w * 0.32
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)
            painter.setBrush(qcolor)
            arrow = QPolygonF(
                [
                    QPointF(w * 0.72, h * 0.30),
                    QPointF(w * 0.88, h * 0.50),
                    QPointF(w * 0.72, h * 0.70),
                ]
            )
            painter.drawPolygon(arrow)
        elif icon_key == "pitch":
            path = QPainterPath()
            path.moveTo(QPointF(w * 0.30, h * 0.75))
            path.cubicTo(QPointF(w * 0.45, h * 0.20), QPointF(w * 0.55, h * 0.20), QPointF(w * 0.70, h * 0.75))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.setBrush(qcolor)
            painter.drawEllipse(QPointF(w * 0.50, h * 0.22), w * 0.10, h * 0.10)
        elif icon_key == "yaw":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(w * 0.18, h * 0.18, w * 0.64, h * 0.64)
            painter.drawArc(rect, 30 * 16, 300 * 16)
            painter.setBrush(qcolor)
            painter.drawEllipse(QPointF(w * 0.50, h * 0.18), w * 0.08, h * 0.08)
        elif icon_key == "temperature":
            rect = QRectF(w * 0.35, h * 0.12, w * 0.30, h * 0.62)
            painter.drawRoundedRect(rect, 4, 4)
            bulb = QRectF(w * 0.30, h * 0.62, w * 0.40, h * 0.26)
            painter.drawEllipse(bulb)
        elif icon_key == "voltage":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(w * 0.20, h * 0.30, w * 0.60, h * 0.40))
            painter.drawLine(QPointF(w * 0.15, h * 0.38), QPointF(w * 0.25, h * 0.38))
            painter.drawLine(QPointF(w * 0.15, h * 0.62), QPointF(w * 0.25, h * 0.62))
        else:  # pragma: no cover - unknown icon fallback
            painter.drawEllipse(center, w * 0.25, h * 0.25)

        painter.end()
        return pixmap



    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._set_collapsed(collapsed)

    def _set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setProperty("collapsed", "true" if collapsed else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        if self._content_frame is not None:
            self._content_frame.setVisible(not collapsed)
        self._apply_toggle_palette()
        self._update_toggle_icon()
        self._update_shadow()
        self.collapsedChanged.emit(collapsed)

    def expand(self) -> None:
        self.set_collapsed(False)

    def collapse(self) -> None:
        self.set_collapsed(True)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def update_sample(self, sample: "SensorSample") -> None:
        values = sample.as_dict()
        for field, label in self._value_labels.items():
            value = values.get(field)
            formatter = self._formatters.get(field, lambda v: str(v))
            if value is None:
                label.setText("--")
            else:
                label.setText(formatter(value))
        self.set_streaming(True)

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        self._set_connection_state("connected" if streaming else "waiting")
        self._apply_toggle_palette()
        self._update_toggle_icon()
        self._update_shadow()

    def _set_connection_state(self, state: str) -> None:
        if state == self._connection_state:
            return
        self._connection_state = state
        if state == "waiting":
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._blink_on = True
        self._update_toggle_icon()
        self._update_shadow()

    def _handle_blink(self) -> None:
        self._blink_on = not self._blink_on
        self._update_toggle_icon()

    def _apply_toggle_palette(self) -> None:
        if self._toggle_button is None:
            return
        palette = (
            "#telemetryToggle {"
            "background-color: transparent;"
            "border: none;"
            "padding: 0px;"
            "}"
            "#telemetryToggle:hover {"
            "background-color: transparent;"
            "}"
        )
        self._toggle_button.setStyleSheet(palette)

    def _update_toggle_icon(self) -> None:
        if self._toggle_button is None:
            return
        color = self._connection_color()
        pulse = self._connection_state == "waiting" and not self._blink_on
        pixmap = self._build_connection_icon(color, pulse)
        self._toggle_button.setIcon(QIcon(pixmap))

    def _update_shadow(self) -> None:
        if self._shadow is None:
            return
        if self._collapsed:
            opacity = 60
        else:
            opacity = 110 if self._streaming else 90
        accent = self._connection_color()
        color = QColor(accent)
        color.setAlpha(opacity)
        self._shadow.setColor(color)

    def _connection_color(self) -> QColor:
        if self._connection_state == "connected":
            return QColor("#2DD881")
        if self._connection_state == "waiting":
            return QColor("#FFD166")
        return QColor("#F94144")

    def _build_connection_icon(self, color: QColor, pulse: bool) -> QPixmap:
        size = 26
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        draw_color = QColor(color)
        if pulse:
            draw_color.setAlphaF(0.4)

        center = QPointF(size / 2.0, size * 0.58)
        base_radius = size * 0.08

        painter.setBrush(draw_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, base_radius, base_radius)

        pen = QPen(draw_color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for i in range(3):
            radius = size * (0.2 + i * 0.12)
            rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
            painter.drawArc(rect, 225 * 16, 90 * 16)
            painter.drawArc(rect, (225 + 180) * 16, 90 * 16)

        painter.end()
        return pixmap


class InfoPanel(CollapsiblePanel):
    """Show device IP and Wi-Fi connection details."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("infoPanel")
        self._ip_label: Optional[QLabel] = None
        self._wifi_label: Optional[QLabel] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15000)
        self._refresh_timer.timeout.connect(self.refresh_info)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._build_ui()
        self.refresh_info()
        self._refresh_timer.start()
        self._apply_collapsed_state(True)

    def _build_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#infoPanel {"
            "background-color: rgba(4, 9, 20, 0.65);"
            "border-radius: 16px;"
            "border: none;"
            "}"
            "#infoPanel QLabel {"
            "color: #e8f1ff;"
            "font-size: 14px;"
            "font-weight: 500;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(6)

        content = QFrame()
        content.setObjectName("infoContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)
        layout.addWidget(content, 1)
        self._content_frame = content

        ip_label = QLabel("IP: --")
        wifi_label = QLabel("Wi-Fi: --")
        content_layout.addWidget(ip_label)
        content_layout.addWidget(wifi_label)
        self._ip_label = ip_label
        self._wifi_label = wifi_label

        self._toggle_button = QPushButton()
        self._toggle_button.setObjectName("infoToggle")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setMinimumSize(26, 26)
        self._toggle_button.setIconSize(QSize(20, 20))
        self._toggle_button.setToolTip("Show device information")
        self._toggle_button.clicked.connect(self.toggle)
        self._toggle_button.setText("")
        layout.addWidget(self._toggle_button, 0, Qt.AlignmentFlag.AlignRight)

        self._shadow = None

    def refresh_info(self) -> None:
        if self._ip_label is not None:
            self._ip_label.setText(f"IP: {_detect_ip_address()}")
        if self._wifi_label is not None:
            self._wifi_label.setText(f"Wi-Fi: {_detect_wifi_name()}")

    def _apply_toggle_palette(self) -> None:
        if self._toggle_button is None:
            return
        self._toggle_button.setStyleSheet(
            "#infoToggle {"
            "background-color: transparent;"
            "border: none;"
            "padding: 0px;"
            "}"
            "#infoToggle:hover {"
            "background-color: transparent;"
            "}"
        )

    def _update_toggle_icon(self) -> None:
        if self._toggle_button is None:
            return
        color = QColor("#4CC9F0")
        if self._collapsed:
            color.setAlphaF(0.85)
        pixmap = self._build_info_icon(color)
        self._toggle_button.setIcon(QIcon(pixmap))

    def _update_shadow(self) -> None:
        if self._shadow is None:
            return
        opacity = 50 if self._collapsed else 95
        color = QColor(76, 201, 240)
        color.setAlpha(opacity)
        self._shadow.setColor(color)

    def _build_info_icon(self, color: QColor) -> QPixmap:
        size = 20
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        center = QPointF(size / 2.0, size / 2.0)
        radius = size * 0.38
        painter.drawEllipse(center, radius, radius)

        painter.drawPoint(QPointF(center.x(), center.y() - radius * 0.35))
        painter.drawLine(
            QPointF(center.x(), center.y() - radius * 0.05),
            QPointF(center.x(), center.y() + radius * 0.35),
        )

        painter.end()
        return pixmap


def _detect_ip_address() -> str:
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    except OSError:
        ip = "Unavailable"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
    return ip


def _detect_wifi_name() -> str:
    detectors = (
        _wifi_from_nmcli,
        _wifi_from_iwgetid,
        _wifi_from_networksetup,
        _wifi_from_netsh,
    )
    for detector in detectors:
        ssid = detector()
        if ssid:
            return ssid
    return "Unavailable"


def _wifi_from_nmcli() -> Optional[str]:
    try:
        result = subprocess.check_output(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in result.splitlines():
        parts = line.strip().split(":", 1)
        if len(parts) == 2 and parts[0] == "yes" and parts[1]:
            return parts[1]
    return None


def _wifi_from_iwgetid() -> Optional[str]:
    try:
        result = subprocess.check_output(["iwgetid", "-r"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    ssid = result.strip()
    return ssid or None


def _wifi_from_networksetup() -> Optional[str]:
    try:
        result = subprocess.check_output(
            ["networksetup", "-getairportnetwork", "en0"], text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    match = re.search(r":\s*(.+)", result.strip())
    if match:
        name = match.group(1).strip()
        if name and name.lower() != "off":
            return name
    return None


def _wifi_from_netsh() -> Optional[str]:
    try:
        result = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"], text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in result.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("ssid") and "bssid" not in stripped.lower():
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                candidate = parts[1].strip()
                if candidate:
                    return candidate
    return None

