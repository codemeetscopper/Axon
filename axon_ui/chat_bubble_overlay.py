"""Robotic-style chat overlay — text on left/right edges without covering the face."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

_MAX_BUBBLES = 6
_BUBBLE_LIFETIME_MS = 12000


class ChatBubbleOverlay(QWidget):
    """Transparent overlay with robotic chat text on left (bot) and right (user)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._bubbles: deque[dict] = deque(maxlen=_MAX_BUBBLES)
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._tick)
        self._fade_timer.start(50)

    def add_user_bubble(self, text: str) -> None:
        self._bubbles.append({
            "text": text, "role": "user", "opacity": 1.0, "age_ms": 0,
        })
        self.update()

    def add_bot_bubble(self, text: str) -> None:
        self._bubbles.append({
            "text": text, "role": "bot", "opacity": 1.0, "age_ms": 0,
        })
        self.update()

    def clear(self) -> None:
        self._bubbles.clear()
        self.update()

    def _tick(self) -> None:
        if not self._bubbles:
            return
        changed = False
        to_remove = []
        for b in self._bubbles:
            b["age_ms"] += 50
            if b["age_ms"] > _BUBBLE_LIFETIME_MS:
                b["opacity"] = max(0.0, b["opacity"] - 0.04)
                changed = True
                if b["opacity"] <= 0.0:
                    to_remove.append(b)
        for b in to_remove:
            self._bubbles.remove(b)
            changed = True
        if changed:
            self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        if not self._bubbles:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont()
        font.setFamily("monospace")
        font.setPixelSize(13)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        col_width = int(self.width() * 0.22)
        margin = 8
        line_h = metrics.height() + 3

        # Separate into left (bot) and right (user) columns
        left_items = [b for b in self._bubbles if b["role"] == "bot"]
        right_items = [b for b in self._bubbles if b["role"] == "user"]

        # Draw left column (bot) — top-aligned, flowing down
        y = margin + 40  # below top HUD area
        for b in left_items:
            alpha = int(b["opacity"] * 200)
            lines = self._wrap(b["text"], metrics, col_width - margin * 2)
            # Accent line
            accent = QColor(0, 220, 180, alpha)
            painter.setPen(QPen(accent, 2.0))
            x0 = margin
            painter.drawLine(x0, int(y), x0, int(y + len(lines) * line_h))
            # Text
            painter.setPen(QColor(0, 220, 180, alpha))
            for line in lines:
                painter.drawText(x0 + 6, int(y + metrics.ascent()), line)
                y += line_h
            y += 8

        # Draw right column (user) — top-aligned, flowing down
        y = margin + 40
        for b in right_items:
            alpha = int(b["opacity"] * 200)
            lines = self._wrap(b["text"], metrics, col_width - margin * 2)
            # Accent line on right
            accent = QColor(100, 160, 255, alpha)
            x_right = self.width() - margin
            painter.setPen(QPen(accent, 2.0))
            painter.drawLine(x_right, int(y), x_right, int(y + len(lines) * line_h))
            # Text — right-aligned
            painter.setPen(QColor(100, 160, 255, alpha))
            for line in lines:
                tw = metrics.horizontalAdvance(line)
                painter.drawText(x_right - 6 - tw, int(y + metrics.ascent()), line)
                y += line_h
            y += 8

        painter.end()

    @staticmethod
    def _wrap(text: str, metrics, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if metrics.horizontalAdvance(test) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]
