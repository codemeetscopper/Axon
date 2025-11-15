from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, Tuple

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


@dataclass
class EmotionPreset:
    name: str
    eye_openness: float
    eye_curve: float
    brow_raise: float
    brow_tilt: float
    mouth_curve: float
    mouth_open: float
    mouth_width: float
    mouth_height: float
    iris_size: float
    cheek_intensity: float
    accent_color: Tuple[int, int, int]


class RoboticFaceWidget(QWidget):
    """Animated robotic face widget with emotion and orientation controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 480)

        self._presets: Dict[str, EmotionPreset] = self._build_presets()
        self._current_emotion = "neutral"
        self._state = self._preset_to_state(self._presets[self._current_emotion])
        self._start_state = self._state.copy()
        self._target_state = self._state.copy()

        self._orientation = {
            "yaw": 0.0,
            "pitch": 0.0,
            "roll": 0.0,
        }

        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.valueChanged.connect(self._update_state_from_animation)
        self._animation.finished.connect(self.update)

        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._update_idle)
        self._idle_timer.start(16)

        self._time = 0.0
        self._breathe_offset = 0.0
        self._sparkle = 0.0
        self._blink_phase = 0.0
        self._blinking = False
        self._next_blink_at = random.uniform(2.0, 5.0)
        self._time_since_blink = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def available_emotions(self) -> Tuple[str, ...]:
        return tuple(self._presets.keys())

    def set_emotion(self, emotion: str) -> None:
        """Animate to the requested emotion."""
        if emotion not in self._presets:
            raise ValueError(f"Unknown emotion '{emotion}'. Available: {self.available_emotions()}")

        if emotion == self._current_emotion:
            return

        self._current_emotion = emotion
        target_state = self._preset_to_state(self._presets[emotion])
        self._start_state = self._state.copy()

        self._animation.stop()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(550)
        self._target_state = target_state
        self._animation.start()

    def set_orientation(self, yaw: float | None = None, pitch: float | None = None, roll: float | None = None) -> None:
        """Update the head orientation in degrees."""
        if yaw is not None:
            self._orientation["yaw"] = float(max(-45.0, min(45.0, yaw)))
        if pitch is not None:
            self._orientation["pitch"] = float(max(-30.0, min(30.0, pitch)))
        if roll is not None:
            self._orientation["roll"] = float(max(-30.0, min(30.0, roll)))
        self.update()

    # ------------------------------------------------------------------
    # Animation helpers
    # ------------------------------------------------------------------
    def _update_state_from_animation(self, progress: float) -> None:
        for key, start_value in self._start_state.items():
            end_value = self._target_state[key]
            if isinstance(start_value, QColor) and isinstance(end_value, QColor):
                interpolated = QColor(
                    start_value.red() + (end_value.red() - start_value.red()) * progress,
                    start_value.green() + (end_value.green() - start_value.green()) * progress,
                    start_value.blue() + (end_value.blue() - start_value.blue()) * progress,
                )
                self._state[key] = interpolated
            else:
                self._state[key] = start_value + (end_value - start_value) * progress
        self.update()

    def _update_idle(self) -> None:
        dt = 0.016
        self._time += dt
        self._time_since_blink += dt

        self._breathe_offset = math.sin(self._time * 0.7) * 6.0
        self._sparkle = (math.sin(self._time * 3.0) + 1.0) * 0.5

        if self._blinking:
            self._blink_phase += dt / 0.18
            if self._blink_phase >= 1.0:
                self._blinking = False
                self._blink_phase = 0.0
        elif self._time_since_blink > self._next_blink_at:
            self._blinking = True
            self._blink_phase = 0.0
            self._time_since_blink = 0.0
            self._next_blink_at = random.uniform(2.0, 5.0)

        self.update()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()

        bg_gradient = QLinearGradient(0, 0, 0, rect.height())
        bg_gradient.setColorAt(0.0, QColor(10, 12, 28))
        bg_gradient.setColorAt(1.0, QColor(2, 4, 12))
        painter.fillRect(rect, bg_gradient)

        face_margin = rect.height() * 0.08
        face_rect = QRectF(rect.left() + face_margin, rect.top() + face_margin, rect.width() - face_margin * 2, rect.height() - face_margin * 2)

        center = face_rect.center()
        painter.save()
        painter.translate(center)
        painter.rotate(self._orientation["roll"] * 0.8)
        painter.translate(-center)

        # Head shadow
        shadow_rect = QRectF(face_rect)
        shadow_rect.translate(0, face_rect.height() * 0.04)
        shadow = QLinearGradient(shadow_rect.topLeft(), shadow_rect.bottomLeft())
        shadow.setColorAt(0.0, QColor(0, 0, 0, 0))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 80))
        painter.setBrush(shadow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(shadow_rect, face_rect.width() * 0.25, face_rect.height() * 0.25)

        head_gradient = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
        head_gradient.setColorAt(0.0, QColor(32, 36, 60))
        head_gradient.setColorAt(0.45, QColor(24, 28, 48))
        head_gradient.setColorAt(1.0, QColor(12, 16, 30))
        painter.setBrush(head_gradient)
        painter.setPen(QPen(QColor(90, 100, 160, 120), face_rect.width() * 0.01))
        painter.drawRoundedRect(face_rect, face_rect.width() * 0.3, face_rect.height() * 0.3)

        accent_color: QColor = self._state["accent_color"]

        # Glowing halo
        halo_gradient = QLinearGradient(center.x(), face_rect.top(), center.x(), face_rect.bottom())
        halo_gradient.setColorAt(0.0, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 90))
        halo_gradient.setColorAt(0.6, QColor(accent_color.red(), accent_color.green(), accent_color.blue(), 10))
        halo_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(halo_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(face_rect.adjusted(-20, -20, 20, 20), face_rect.width() * 0.32, face_rect.height() * 0.32)

        eye_height = face_rect.height() * 0.22
        eye_width = face_rect.width() * 0.22
        eye_spacing = face_rect.width() * 0.16

        yaw_offset = self._orientation["yaw"] / 45.0
        pitch_offset = self._orientation["pitch"] / 45.0

        left_eye_center = QPointF(center.x() - eye_spacing, center.y() - face_rect.height() * 0.05 + pitch_offset * 12.0)
        right_eye_center = QPointF(center.x() + eye_spacing, center.y() - face_rect.height() * 0.05 + pitch_offset * 12.0)

        eye_openness = max(0.05, min(1.3, self._state["eye_openness"]))
        eye_curve = self._state["eye_curve"]
        brow_raise = self._state["brow_raise"]
        brow_tilt = self._state["brow_tilt"]
        iris_size = self._state["iris_size"]

        blink_factor = 1.0
        if self._blinking:
            blink_factor -= math.sin(min(1.0, self._blink_phase) * math.pi)
            blink_factor = max(0.0, blink_factor)
        effective_openness = max(0.02, eye_openness * blink_factor)

        sparkle = 0.4 + self._sparkle * 0.6

        for eye_center, direction in ((left_eye_center, -1), (right_eye_center, 1)):
            self._draw_eye(
                painter,
                eye_center,
                eye_width,
                eye_height,
                effective_openness,
                eye_curve * direction,
                iris_size,
                yaw_offset * direction,
                pitch_offset,
                accent_color,
                sparkle,
            )

        self._draw_brows(painter, left_eye_center, right_eye_center, eye_width, brow_raise, brow_tilt, accent_color)
        self._draw_mouth(painter, center, face_rect, accent_color)
        self._draw_cheeks(painter, left_eye_center, right_eye_center, face_rect, accent_color)

        painter.restore()

        self._draw_overlay_highlights(painter, face_rect)

    # ------------------------------------------------------------------
    # Feature drawing helpers
    # ------------------------------------------------------------------
    def _draw_eye(
        self,
        painter: QPainter,
        center: QPointF,
        width: float,
        height: float,
        openness: float,
        curve: float,
        iris_scale: float,
        yaw_offset: float,
        pitch_offset: float,
        accent: QColor,
        sparkle: float,
    ) -> None:
        vertical_scale = openness
        eye_rect = QRectF(
            center.x() - width * 0.5,
            center.y() - height * vertical_scale * 0.5 + self._breathe_offset * 0.1,
            width,
            height * vertical_scale,
        )

        lid_path = QPainterPath()
        left = eye_rect.topLeft()
        right = eye_rect.topRight()
        bottom_left = eye_rect.bottomLeft()
        bottom_right = eye_rect.bottomRight()

        control_offset = height * 0.5 * (1.0 + curve)
        lid_path.moveTo(left)
        lid_path.cubicTo(
            QPointF(eye_rect.center().x() - width * 0.2, eye_rect.top() - control_offset),
            QPointF(eye_rect.center().x() + width * 0.2, eye_rect.top() - control_offset),
            right,
        )
        lid_path.cubicTo(
            QPointF(eye_rect.center().x() + width * 0.25, eye_rect.bottom() + control_offset * 0.6),
            QPointF(eye_rect.center().x() - width * 0.25, eye_rect.bottom() + control_offset * 0.6),
            left,
        )

        eye_gradient = QLinearGradient(eye_rect.topLeft(), eye_rect.bottomLeft())
        eye_gradient.setColorAt(0.0, QColor(220, 230, 255, 245))
        eye_gradient.setColorAt(1.0, QColor(120, 140, 220, 220))

        painter.setBrush(eye_gradient)
        painter.setPen(QPen(QColor(70, 80, 140), max(2.0, width * 0.04)))
        painter.drawPath(lid_path)

        iris_radius = min(width, height) * 0.32 * iris_scale
        iris_offset_x = yaw_offset * width * 0.45
        iris_offset_y = pitch_offset * height * 0.28
        iris_center = QPointF(center.x() + iris_offset_x, center.y() + iris_offset_y)

        iris_gradient = QLinearGradient(iris_center.x(), iris_center.y() - iris_radius, iris_center.x(), iris_center.y() + iris_radius)
        iris_gradient.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 230))
        iris_gradient.setColorAt(1.0, QColor(20, 30, 60, 230))

        painter.setBrush(iris_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(iris_center, iris_radius, iris_radius)

        pupil_radius = iris_radius * 0.45
        painter.setBrush(QColor(10, 12, 20))
        painter.drawEllipse(iris_center, pupil_radius, pupil_radius)

        highlight_radius = iris_radius * (0.22 + sparkle * 0.12)
        highlight_center = QPointF(iris_center.x() - pupil_radius * 0.45, iris_center.y() - pupil_radius * 0.55)
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawEllipse(highlight_center, highlight_radius, highlight_radius)

        lower_highlight_center = QPointF(iris_center.x() + pupil_radius * 0.3, iris_center.y() + pupil_radius * 0.4)
        painter.setBrush(QColor(255, 255, 255, int(90 * sparkle)))
        painter.drawEllipse(lower_highlight_center, highlight_radius * 0.4, highlight_radius * 0.4)

    def _draw_brows(
        self,
        painter: QPainter,
        left_center: QPointF,
        right_center: QPointF,
        eye_width: float,
        raise_amount: float,
        tilt: float,
        accent: QColor,
    ) -> None:
        brow_width = eye_width * 1.1
        brow_height = eye_width * 0.25
        offset_y = -eye_width * (0.55 + raise_amount * 0.4)

        for center, direction in ((left_center, -1), (right_center, 1)):
            brow_rect = QRectF(
                center.x() - brow_width * 0.5,
                center.y() + offset_y,
                brow_width,
                brow_height,
            )
            rotation = tilt * 18.0 * direction

            painter.save()
            painter.translate(brow_rect.center())
            painter.rotate(rotation)
            painter.translate(-brow_rect.center())

            gradient = QLinearGradient(brow_rect.topLeft(), brow_rect.bottomRight())
            gradient.setColorAt(0.0, QColor(10, 12, 20))
            gradient.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue()))

            path = QPainterPath()
            path.addRoundedRect(brow_rect, brow_height * 0.8, brow_height * 0.8)
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.restore()

    def _draw_mouth(self, painter: QPainter, center: QPointF, face_rect: QRectF, accent: QColor) -> None:
        mouth_width = face_rect.width() * 0.42 * self._state["mouth_width"]
        mouth_height = face_rect.height() * 0.18 * self._state["mouth_height"]
        mouth_curve = self._state["mouth_curve"]
        mouth_open = self._state["mouth_open"]

        base_y = center.y() + face_rect.height() * 0.28 + self._breathe_offset * 0.25

        left = QPointF(center.x() - mouth_width * 0.5, base_y)
        right = QPointF(center.x() + mouth_width * 0.5, base_y)
        control_top = QPointF(center.x(), base_y - mouth_height * (0.6 + mouth_curve))
        control_bottom = QPointF(center.x(), base_y + mouth_height * (0.4 + mouth_open))

        path = QPainterPath(left)
        path.quadTo(control_top, right)
        path.quadTo(control_bottom, left)
        path.closeSubpath()

        gradient = QLinearGradient(left, QPointF(left.x(), base_y + mouth_height))
        gradient.setColorAt(0.0, QColor(20, 10, 20, 240))
        gradient.setColorAt(0.7, QColor(accent.red(), accent.green(), accent.blue(), 220))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 120))

        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 80), 2.0))
        painter.drawPath(path)

        if mouth_open > 0.2:
            inner_path = QPainterPath(left)
            inner_top = QPointF(center.x(), base_y - mouth_height * (0.4 + mouth_curve * 0.5))
            inner_bottom = QPointF(center.x(), base_y + mouth_height * (0.8 + mouth_open))
            inner_path.quadTo(inner_top, right)
            inner_path.quadTo(inner_bottom, left)
            inner_path.closeSubpath()

            painter.setBrush(QColor(255, 255, 255, 35))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(inner_path)

    def _draw_cheeks(
        self,
        painter: QPainter,
        left_center: QPointF,
        right_center: QPointF,
        face_rect: QRectF,
        accent: QColor,
    ) -> None:
        cheek_intensity = self._state["cheek_intensity"]
        if cheek_intensity <= 0.01:
            return

        radius = face_rect.width() * 0.12
        alpha = int(90 + 120 * cheek_intensity)
        color = QColor(accent.red(), accent.green(), accent.blue(), alpha)

        for center in (left_center, right_center):
            offset = QPointF(0, face_rect.height() * 0.12)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(center + offset, radius, radius * 0.75)

    def _draw_overlay_highlights(self, painter: QPainter, face_rect: QRectF) -> None:
        top_glow = QLinearGradient(face_rect.topLeft(), face_rect.topRight())
        top_glow.setColorAt(0.0, QColor(255, 255, 255, 20))
        top_glow.setColorAt(0.5, QColor(255, 255, 255, 60))
        top_glow.setColorAt(1.0, QColor(255, 255, 255, 20))

        painter.setBrush(top_glow)
        painter.setPen(Qt.PenStyle.NoPen)
        highlight_rect = QRectF(
            face_rect.left() + face_rect.width() * 0.1,
            face_rect.top() + face_rect.height() * 0.05,
            face_rect.width() * 0.8,
            face_rect.height() * 0.18,
        )
        painter.drawRoundedRect(highlight_rect, face_rect.width() * 0.2, face_rect.height() * 0.2)

        bottom_glow = QLinearGradient(face_rect.bottomLeft(), face_rect.bottomRight())
        bottom_glow.setColorAt(0.0, QColor(255, 255, 255, 12))
        bottom_glow.setColorAt(0.5, QColor(255, 255, 255, 35))
        bottom_glow.setColorAt(1.0, QColor(255, 255, 255, 12))

        bottom_rect = QRectF(
            face_rect.left() + face_rect.width() * 0.18,
            face_rect.bottom() - face_rect.height() * 0.18,
            face_rect.width() * 0.64,
            face_rect.height() * 0.12,
        )
        painter.drawRoundedRect(bottom_rect, face_rect.width() * 0.15, face_rect.height() * 0.15)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _build_presets(self) -> Dict[str, EmotionPreset]:
        return {
            "neutral": EmotionPreset(
                name="neutral",
                eye_openness=1.0,
                eye_curve=0.0,
                brow_raise=0.0,
                brow_tilt=0.0,
                mouth_curve=0.2,
                mouth_open=0.1,
                mouth_width=1.0,
                mouth_height=1.0,
                iris_size=1.0,
                cheek_intensity=0.1,
                accent_color=(70, 200, 255),
            ),
            "happy": EmotionPreset(
                name="happy",
                eye_openness=1.2,
                eye_curve=0.35,
                brow_raise=0.35,
                brow_tilt=-0.2,
                mouth_curve=0.8,
                mouth_open=0.3,
                mouth_width=1.05,
                mouth_height=1.2,
                iris_size=1.05,
                cheek_intensity=0.7,
                accent_color=(90, 240, 210),
            ),
            "sad": EmotionPreset(
                name="sad",
                eye_openness=0.85,
                eye_curve=-0.45,
                brow_raise=-0.3,
                brow_tilt=0.35,
                mouth_curve=-0.6,
                mouth_open=0.05,
                mouth_width=0.85,
                mouth_height=0.9,
                iris_size=0.95,
                cheek_intensity=0.25,
                accent_color=(140, 120, 255),
            ),
            "surprised": EmotionPreset(
                name="surprised",
                eye_openness=1.45,
                eye_curve=0.1,
                brow_raise=0.5,
                brow_tilt=0.0,
                mouth_curve=0.2,
                mouth_open=0.9,
                mouth_width=0.95,
                mouth_height=1.4,
                iris_size=1.15,
                cheek_intensity=0.4,
                accent_color=(255, 200, 120),
            ),
            "sleepy": EmotionPreset(
                name="sleepy",
                eye_openness=0.35,
                eye_curve=-0.2,
                brow_raise=-0.15,
                brow_tilt=-0.1,
                mouth_curve=0.0,
                mouth_open=0.05,
                mouth_width=0.9,
                mouth_height=0.7,
                iris_size=0.9,
                cheek_intensity=0.15,
                accent_color=(120, 180, 255),
            ),
            "curious": EmotionPreset(
                name="curious",
                eye_openness=1.1,
                eye_curve=0.15,
                brow_raise=0.15,
                brow_tilt=0.4,
                mouth_curve=0.35,
                mouth_open=0.18,
                mouth_width=1.0,
                mouth_height=1.0,
                iris_size=1.1,
                cheek_intensity=0.5,
                accent_color=(255, 120, 210),
            ),
            "excited": EmotionPreset(
                name="excited",
                eye_openness=1.35,
                eye_curve=0.45,
                brow_raise=0.4,
                brow_tilt=-0.25,
                mouth_curve=1.1,
                mouth_open=0.75,
                mouth_width=1.1,
                mouth_height=1.3,
                iris_size=1.08,
                cheek_intensity=0.85,
                accent_color=(255, 140, 100),
            ),
        }

    def _preset_to_state(self, preset: EmotionPreset) -> Dict[str, object]:
        return {
            "eye_openness": preset.eye_openness,
            "eye_curve": preset.eye_curve,
            "brow_raise": preset.brow_raise,
            "brow_tilt": preset.brow_tilt,
            "mouth_curve": preset.mouth_curve,
            "mouth_open": preset.mouth_open,
            "mouth_width": preset.mouth_width,
            "mouth_height": preset.mouth_height,
            "iris_size": preset.iris_size,
            "cheek_intensity": preset.cheek_intensity,
            "accent_color": QColor(*preset.accent_color),
        }
