from __future__ import annotations

import logging
import signal
import sys
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from robot_control import EmotionPolicy, FaceController, SerialReader
from robot_control.sensor_data import SensorSample
from robotic_face_widget import RoboticFaceWidget

try:  # Reuse the palette from the interactive demo when available.
    from app_palette import apply_dark_palette as apply_palette
except Exception:  # pragma: no cover - best effort reuse
    apply_palette = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


Formatter = Callable[[float], str]


class TelemetryPanel(QFrame):
    """Display the latest telemetry sample."""

    collapsedChanged = Signal(bool)

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
        self._toggle_button: Optional[QPushButton] = None
        self._content_frame: Optional[QFrame] = None
        self._layout: Optional[QHBoxLayout] = None
        self._collapsed = True
        self._streaming = False
        self._shadow: Optional[QGraphicsDropShadowEffect] = None
        self.setObjectName("telemetryPanel")
        self._build_ui()
        self.set_streaming(False)
        self._set_collapsed(False)

    def _build_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            "#telemetryPanel {"
            "background-color: rgba(10, 18, 38, 0.22);"
            "border-radius: 18px;"
            "border: 1px solid rgba(90, 120, 190, 0.28);"
            "}"
            "#telemetryPanel[collapsed=\"true\"] {"
            "background-color: rgba(10, 18, 38, 0.32);"
            "}"
            "#telemetryPanel QLabel {"
            "color: #e8f1ff;"
            "font-size: 14px;"
            "font-weight: 500;"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        self._layout = layout

        self._toggle_button = QPushButton()
        self._toggle_button.setObjectName("telemetryToggle")
        self._toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_button.setMinimumSize(88, 32)
        self._toggle_button.setToolTip("Show/Hide telemetry")
        self._toggle_button.clicked.connect(self.toggle)
        self._toggle_button.setText("Telemetry")
        layout.addWidget(self._toggle_button, 0, Qt.AlignmentFlag.AlignLeft)

        content = QFrame()
        content.setObjectName("telemetryContent")
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        layout.addWidget(content, 1)

        self._content_frame = content

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
                f"color: {color}; font-size: 14px; font-weight: 600;"
            )
            value_label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            content_layout.addWidget(value_label)
            self._value_labels[field] = value_label
            self._formatters[field] = formatter

            if index < len(self._FIELDS) - 1:
                separator = QFrame()
                separator.setObjectName("telemetrySeparator")
                separator.setFixedSize(1, 18)
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

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)
        self._shadow = shadow
        self._update_shadow()

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
            painter.drawLine(QPointF(w * 0.50, h * 0.20), QPointF(w * 0.50, h * 0.80))
            up = QPolygonF(
                [
                    QPointF(w * 0.50, h * 0.18),
                    QPointF(w * 0.38, h * 0.36),
                    QPointF(w * 0.62, h * 0.36),
                ]
            )
            down = QPolygonF(
                [
                    QPointF(w * 0.50, h * 0.82),
                    QPointF(w * 0.38, h * 0.64),
                    QPointF(w * 0.62, h * 0.64),
                ]
            )
            painter.drawPolygon(up)
            painter.drawPolygon(down)
        elif icon_key == "yaw":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, w * 0.34, h * 0.34)
            painter.drawLine(QPointF(w * 0.50, h * 0.20), QPointF(w * 0.50, h * 0.80))
            painter.drawLine(QPointF(w * 0.20, h * 0.50), QPointF(w * 0.80, h * 0.50))
            painter.setBrush(qcolor)
            painter.drawEllipse(QPointF(w * 0.50, h * 0.50), w * 0.08, h * 0.08)
        elif icon_key == "temperature":
            bulb_center = QPointF(w * 0.48, h * 0.74)
            painter.drawEllipse(bulb_center, w * 0.18, h * 0.18)
            painter.drawRoundedRect(
                QRectF(w * 0.42, h * 0.26, w * 0.12, h * 0.48),
                w * 0.06,
                h * 0.06,
            )
        elif icon_key == "voltage":
            path = QPainterPath()
            path.moveTo(w * 0.36, h * 0.16)
            path.lineTo(w * 0.60, h * 0.16)
            path.lineTo(w * 0.46, h * 0.48)
            path.lineTo(w * 0.68, h * 0.48)
            path.lineTo(w * 0.32, h * 0.84)
            path.lineTo(w * 0.44, h * 0.52)
            path.lineTo(w * 0.28, h * 0.52)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.setBrush(qcolor)
            painter.drawEllipse(center, w * 0.24, h * 0.24)

        painter.end()
        return pixmap

    def _build_toggle_icon(self, expanded: bool) -> QIcon:
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        accent = QColor("#2DD881") if self._streaming else QColor("#9AA2B8")
        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)

        if expanded:
            points = QPolygonF(
                [
                    QPointF(size * 0.64, size * 0.22),
                    QPointF(size * 0.36, size * 0.50),
                    QPointF(size * 0.64, size * 0.78),
                ]
            )
        else:
            points = QPolygonF(
                [
                    QPointF(size * 0.36, size * 0.22),
                    QPointF(size * 0.64, size * 0.50),
                    QPointF(size * 0.36, size * 0.78),
                ]
            )
        painter.drawPolygon(points)
        painter.end()
        return QIcon(pixmap)

    def toggle(self) -> None:
        self._set_collapsed(not self._collapsed)

    def expand(self) -> None:
        self._set_collapsed(False)

    def collapse(self) -> None:
        self._set_collapsed(True)

    def _set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return

        self._collapsed = collapsed
        if self._content_frame is None or self._toggle_button is None:
            return

        if collapsed:
            self._content_frame.setVisible(False)
            self._content_frame.setMaximumWidth(0)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            toggle_width = self._toggle_button.sizeHint().width()
            pill_width = toggle_width + 18
            self.setMinimumWidth(pill_width)
            self.setMaximumWidth(pill_width)
            if self._layout is not None:
                self._layout.setContentsMargins(6, 6, 6, 6)
        else:
            self._content_frame.setVisible(True)
            self._content_frame.setMaximumWidth(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.setMaximumWidth(16777215)
            self.setMinimumWidth(0)
            if self._layout is not None:
                self._layout.setContentsMargins(14, 10, 14, 10)

        self.setProperty("collapsed", collapsed)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self._update_toggle_icon()
        self._update_shadow()
        self.updateGeometry()
        self.collapsedChanged.emit(collapsed)

    def _update_toggle_icon(self) -> None:
        if self._toggle_button is None:
            return
        icon = self._build_toggle_icon(expanded=not self._collapsed)
        self._toggle_button.setIcon(icon)
        self._toggle_button.setIconSize(QSize(20, 20))

    def _apply_toggle_palette(self) -> None:
        if self._toggle_button is None:
            return
        accent = "#2DD881" if self._streaming else "#9AA2B8"
        base_bg = "rgba(45, 216, 129, 0.22)" if self._streaming else "rgba(154, 162, 184, 0.26)"
        hover_bg = "rgba(45, 216, 129, 0.32)" if self._streaming else "rgba(154, 162, 184, 0.38)"
        pressed_bg = "rgba(45, 216, 129, 0.44)" if self._streaming else "rgba(154, 162, 184, 0.50)"
        self._toggle_button.setStyleSheet(
            "#telemetryToggle {"
            f"background-color: {base_bg};"
            "border: none;"
            "border-radius: 18px;"
            f"color: {accent};"
            "padding: 6px 12px;"
            "}"
            "#telemetryToggle:hover {"
            f"background-color: {hover_bg};"
            "}"
            "#telemetryToggle:pressed {"
            f"background-color: {pressed_bg};"
            "}"
        )

    def is_collapsed(self) -> bool:
        return self._collapsed

    def update_sample(self, sample: SensorSample) -> None:
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
        self._apply_toggle_palette()
        self._update_toggle_icon()
        self._update_shadow()

    def _update_shadow(self) -> None:
        if self._shadow is None:
            return
        if self._collapsed:
            opacity = 70
        else:
            opacity = 110 if self._streaming else 90
        accent = QColor("#2DD881") if self._streaming else QColor("#6B7791")
        color = QColor(accent)
        color.setAlpha(opacity)
        self._shadow.setColor(color)


class RobotMainWindow(QWidget):
    def __init__(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        super().__init__()
        self.setWindowTitle("Axon Runtime")
        self._build_ui(face, telemetry)

    def _build_ui(self, face: RoboticFaceWidget, telemetry: TelemetryPanel) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        screen = QWidget(self)
        stack = QStackedLayout(screen)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(0)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        face.setParent(screen)
        face.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stack.addWidget(face)

        overlay = QWidget(screen)
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(16, 16, 16, 16)
        overlay_layout.setSpacing(0)
        overlay_layout.addStretch(1)

        dock = QWidget(overlay)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(0)
        dock_layout.addWidget(telemetry)
        dock_layout.addStretch(1)
        overlay_layout.addWidget(dock, 0, Qt.AlignmentFlag.AlignLeft)

        stack.addWidget(overlay)
        layout.addWidget(screen)


class RobotRuntime(QWidget):
    """Manage the serial polling loop inside the Qt event loop."""

    def __init__(
        self,
        reader: SerialReader,
        controller: FaceController,
        telemetry: TelemetryPanel,
        poll_interval_ms: int = 40,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._reader = reader
        self._controller = controller
        self._telemetry = telemetry
        self._timer = QTimer(self)
        self._timer.setInterval(poll_interval_ms)
        self._timer.timeout.connect(self._poll)
        self._missed_cycles = 0
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._reader.start()
        self._timer.start()

    def stop(self) -> None:
        if not self._running:
            self._reader.stop()
            return
        self._running = False
        self._timer.stop()
        self._reader.stop()

    def _poll(self) -> None:
        sample = self._reader.pop_latest()
        if sample is None:
            self._missed_cycles += 1
            if self._missed_cycles >= 10:
                self._telemetry.set_streaming(False)
            return

        self._missed_cycles = 0
        self._controller.apply_sample(sample)
        self._telemetry.update_sample(sample)


DEFAULT_SERIAL_PORT = "/dev/ttyAMA0"
DEFAULT_BAUDRATE = 115200
DEFAULT_POLL_INTERVAL_MS = 40
DEFAULT_LOG_LEVEL = "INFO"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    _configure_logging(DEFAULT_LOG_LEVEL)

    try:
        reader = SerialReader(port=DEFAULT_SERIAL_PORT, baudrate=DEFAULT_BAUDRATE)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Axon Runtime")
    app.setStyle("Fusion")

    if apply_palette is not None:
        apply_palette(app)

    face = RoboticFaceWidget()
    controller = FaceController(face, EmotionPolicy())
    telemetry = TelemetryPanel()
    window = RobotMainWindow(face, telemetry)

    runtime = RobotRuntime(
        reader,
        controller,
        telemetry,
        poll_interval_ms=DEFAULT_POLL_INTERVAL_MS,
    )
    app.aboutToQuit.connect(runtime.stop)

    # Support clean shutdown when Ctrl+C is pressed on the console.
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    runtime.start()
    window.showFullScreen()

    try:
        return app.exec()
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received; shutting down.")
        app.quit()
        return 0
    finally:
        runtime.stop()


if __name__ == "__main__":
    sys.exit(main())
