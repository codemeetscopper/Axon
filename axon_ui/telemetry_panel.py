"""Telemetry overlay widget that mirrors sensor readings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from axon_ui.collapsible_panel import CollapsiblePanel

if TYPE_CHECKING:
    from robot_control.sensor_data import SensorSample

Formatter = Callable[[float], str]


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
            path.cubicTo(
                QPointF(w * 0.45, h * 0.20),
                QPointF(w * 0.55, h * 0.20),
                QPointF(w * 0.70, h * 0.75),
            )
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

    def _apply_toggle_palette(self) -> None:  # pragma: no cover - Qt painting
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

    def _update_toggle_icon(self) -> None:  # pragma: no cover - Qt painting
        if self._toggle_button is None:
            return
        color = self._connection_color()
        pulse = self._connection_state == "waiting" and not self._blink_on
        pixmap = self._build_connection_icon(color, pulse)
        self._toggle_button.setIcon(QIcon(pixmap))

    def _update_shadow(self) -> None:  # pragma: no cover - Qt painting
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
            draw_color.setAlpha(120)
        center = QPointF(size / 2.0, size / 2.0)
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
