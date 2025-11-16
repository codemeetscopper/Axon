"""Info panel overlay that reports IP and Wi-Fi metadata."""

from __future__ import annotations

import re
import socket
import subprocess
from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from axon_ui.collapsible_panel import CollapsiblePanel


class InfoPanel(CollapsiblePanel):
    """Show device IP and Wi-Fi connection details."""

    displayModeToggleRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("infoPanel")
        self._ip_label: Optional[QLabel] = None
        self._wifi_label: Optional[QLabel] = None
        self._fullscreen_button: Optional[QPushButton] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15000)
        self._refresh_timer.timeout.connect(self.refresh_info)
        self._manual_ip: Optional[str] = None
        self._manual_wifi: Optional[str] = None
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._build_ui()
        self.refresh_info()
        self._refresh_timer.start()
        self._apply_collapsed_state(True)

    def set_manual_entries(self, *, ip: Optional[str] = None, wifi: Optional[str] = None) -> None:
        """Override the detected IP/Wi-Fi values with manual strings."""

        self._manual_ip = ip
        self._manual_wifi = wifi
        if ip is not None or wifi is not None:
            self._refresh_timer.stop()
        else:
            self._refresh_timer.start()
        self.refresh_info()

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
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        layout.addWidget(content, 1)
        self._content_frame = content

        ip_label = QLabel("IP: --")
        wifi_label = QLabel("Wi-Fi: --")
        for label in (ip_label, wifi_label):
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        content_layout.addWidget(ip_label)
        content_layout.addWidget(self._build_separator())
        content_layout.addWidget(wifi_label)
        self._ip_label = ip_label
        self._wifi_label = wifi_label

        content_layout.addWidget(self._build_fullscreen_button())
        content_layout.addStretch(1)

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
        ip_value = self._manual_ip if self._manual_ip is not None else _detect_ip_address()
        wifi_value = self._manual_wifi if self._manual_wifi is not None else _detect_wifi_name()
        if self._ip_label is not None:
            self._ip_label.setText(f"IP: {ip_value}")
        if self._wifi_label is not None:
            self._wifi_label.setText(f"Wi-Fi: {wifi_value}")

    def _build_separator(self) -> QFrame:
        separator = QFrame()
        separator.setObjectName("infoSeparator")
        separator.setFixedSize(1, 18)
        separator.setStyleSheet(
            "QFrame#infoSeparator {"
            "background-color: rgba(232, 241, 255, 0.12);"
            "border: none;"
            "}"
        )
        return separator

    def _build_fullscreen_button(self) -> QPushButton:
        button = QPushButton()
        button.setObjectName("fullscreenToggle")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(28, 28)
        button.setIconSize(QSize(20, 20))
        button.setToolTip("Toggle fullscreen")
        button.setText("")
        button.clicked.connect(self.displayModeToggleRequested.emit)
        self._fullscreen_button = button
        self._apply_fullscreen_icon()
        button.setStyleSheet(
            "#fullscreenToggle {"
            "background-color: rgba(255, 255, 255, 0.08);"
            "border-radius: 14px;"
            "border: none;"
            "}"
        )
        return button

    def _apply_fullscreen_icon(self) -> None:
        if self._fullscreen_button is None:
            return
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor("#4CC9F0")
        pen = QPen(color)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = pixmap.rect().adjusted(4, 4, -4, -4)
        painter.drawRoundedRect(rect, 4, 4)
        painter.end()
        self._fullscreen_button.setIcon(QIcon(pixmap))

    def _apply_toggle_palette(self) -> None:  # pragma: no cover - Qt painting
        if self._toggle_button is None:
            return
        if self._collapsed:
            self._toggle_button.setStyleSheet(
                "background-color: rgba(255, 255, 255, 0.08); border-radius: 13px;"
            )
        else:
            self._toggle_button.setStyleSheet(
                "background-color: rgba(255, 255, 255, 0.18); border-radius: 13px;"
            )

    def _update_toggle_icon(self) -> None:  # pragma: no cover - Qt painting
        if self._toggle_button is None:
            return
        pixmap = self._build_info_icon(QColor("#4CC9F0"))
        self._toggle_button.setIcon(QIcon(pixmap))

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
