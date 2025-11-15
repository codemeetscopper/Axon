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
        face_rect = QRectF(
            rect.left() + face_margin,
            rect.top() + face_margin,
            rect.width() - face_margin * 2,
            rect.height() - face_margin * 2,
        )

        center = face_rect.center()
        head_size = min(face_rect.width(), face_rect.height()) * 0.92
        face_rect = QRectF(
            center.x() - head_size * 0.5,
            center.y() - head_size * 0.5,
            head_size,
            head_size,
        )
        center = face_rect.center()
        painter.save()
        painter.translate(center)
        painter.rotate(self._orientation["roll"] * 0.8)
        painter.translate(-center)

        head_gradient = QLinearGradient(face_rect.topLeft(), face_rect.bottomLeft())
        head_gradient.setColorAt(0.0, QColor(40, 48, 82))
        head_gradient.setColorAt(0.4, QColor(26, 32, 58))
        head_gradient.setColorAt(1.0, QColor(10, 14, 28))
        painter.setBrush(head_gradient)
        painter.setPen(QPen(QColor(110, 140, 220, 140), face_rect.width() * 0.012))
        head_path = QPainterPath()
        head_path.addEllipse(face_rect)
        painter.drawPath(head_path)

        accent_color: QColor = self._state["accent_color"]

        eye_height = face_rect.height() * 0.24
        eye_width = face_rect.width() * 0.26
        eye_spacing = face_rect.width() * 0.18

        yaw_offset = self._orientation["yaw"] / 45.0
        pitch_offset = self._orientation["pitch"] / 45.0
        eye_center_offset_x = yaw_offset * face_rect.width() * 0.05

        left_eye_center = QPointF(
            center.x() - eye_spacing + eye_center_offset_x,
            center.y() - face_rect.height() * 0.05 + pitch_offset * 14.0,
        )
        right_eye_center = QPointF(
            center.x() + eye_spacing + eye_center_offset_x,
            center.y() - face_rect.height() * 0.05 + pitch_offset * 14.0,
        )

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
                yaw_offset,
                pitch_offset,
                accent_color,
                sparkle,
            )

        self._draw_brows(painter, left_eye_center, right_eye_center, eye_width, brow_raise, brow_tilt, accent_color)
        self._draw_mouth(painter, center, face_rect, accent_color)

        painter.restore()

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
        scaled_height = height * vertical_scale
        eye_rect = QRectF(
            center.x() - width * 0.5,
            center.y() - scaled_height * 0.5 + self._breathe_offset * 0.1,
            width,
            scaled_height,
        )

        painter.save()
        painter.translate(eye_rect.center())
        painter.rotate(curve * 12.0)
        painter.translate(-eye_rect.center())

        outer_path = QPainterPath()
        outer_path.addRoundedRect(eye_rect, width * 0.45, scaled_height * 0.45)

        eye_gradient = QLinearGradient(eye_rect.topLeft(), eye_rect.bottomLeft())
        eye_gradient.setColorAt(0.0, QColor(235, 240, 255, 235))
        eye_gradient.setColorAt(0.4, QColor(195, 205, 255, 230))
        eye_gradient.setColorAt(1.0, QColor(120, 140, 220, 215))

        painter.setBrush(eye_gradient)
        painter.setPen(QPen(QColor(70, 90, 160), max(2.0, width * 0.035)))
        painter.drawPath(outer_path)

        iris_radius = min(width, scaled_height) * 0.32 * iris_scale
        iris_offset_x = yaw_offset * width * 0.45
        iris_offset_y = pitch_offset * scaled_height * 0.35
        iris_center = QPointF(center.x() + iris_offset_x, center.y() + iris_offset_y)

        iris_gradient = QLinearGradient(iris_center.x(), iris_center.y() - iris_radius, iris_center.x(), iris_center.y() + iris_radius)
        iris_gradient.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 240))
        iris_gradient.setColorAt(0.6, QColor(40, 60, 100, 230))
        iris_gradient.setColorAt(1.0, QColor(10, 20, 40, 230))

        painter.setBrush(iris_gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(iris_center, iris_radius, iris_radius)

        pupil_radius = iris_radius * 0.48
        painter.setBrush(QColor(8, 10, 18))
        painter.drawEllipse(iris_center, pupil_radius, pupil_radius)

        highlight_radius = iris_radius * (0.24 + sparkle * 0.12)
        highlight_center = QPointF(iris_center.x() - pupil_radius * 0.45, iris_center.y() - pupil_radius * 0.55)
        painter.setBrush(QColor(255, 255, 255, 220))
        painter.drawEllipse(highlight_center, highlight_radius, highlight_radius)

        lower_highlight_center = QPointF(iris_center.x() + pupil_radius * 0.3, iris_center.y() + pupil_radius * 0.4)
        painter.setBrush(QColor(255, 255, 255, int(90 * sparkle)))
        painter.drawEllipse(lower_highlight_center, highlight_radius * 0.4, highlight_radius * 0.4)

        lid_shine = QLinearGradient(eye_rect.topLeft(), eye_rect.topRight())
        lid_shine.setColorAt(0.0, QColor(255, 255, 255, 35))
        lid_shine.setColorAt(0.5, QColor(255, 255, 255, 80))
        lid_shine.setColorAt(1.0, QColor(255, 255, 255, 35))
        painter.setBrush(lid_shine)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            QRectF(
                eye_rect.left() + eye_rect.width() * 0.1,
                eye_rect.top() + eye_rect.height() * 0.05,
                eye_rect.width() * 0.8,
                eye_rect.height() * 0.35,
            ),
            eye_rect.height() * 0.15,
            eye_rect.height() * 0.15,
        )

        painter.restore()

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
        mouth_width = face_rect.width() * 0.44 * self._state["mouth_width"]
        mouth_height = face_rect.height() * 0.2 * self._state["mouth_height"]
        mouth_curve = self._state["mouth_curve"]
        mouth_open = self._state["mouth_open"]

        yaw_offset = self._orientation["yaw"] / 45.0
        base_y = center.y() + face_rect.height() * 0.28 + self._breathe_offset * 0.25
        mouth_center_offset = yaw_offset * face_rect.width() * 0.06

        smile_lift = mouth_height * (0.3 * mouth_curve)
        left_corner = QPointF(center.x() - mouth_width * 0.5 + mouth_center_offset, base_y - smile_lift)
        right_corner = QPointF(center.x() + mouth_width * 0.5 + mouth_center_offset, base_y - smile_lift)

        top_ctrl_y = base_y - mouth_height * (0.28 + mouth_curve * 0.7)
        bottom_ctrl_y = base_y + mouth_height * (0.45 + mouth_open * 1.1)

        outer_path = QPainterPath(left_corner)
        outer_path.cubicTo(
            QPointF(left_corner.x() + mouth_width * 0.22, top_ctrl_y),
            QPointF(right_corner.x() - mouth_width * 0.22, top_ctrl_y),
            right_corner,
        )
        outer_path.cubicTo(
            QPointF(right_corner.x() - mouth_width * 0.2, bottom_ctrl_y),
            QPointF(left_corner.x() + mouth_width * 0.2, bottom_ctrl_y),
            left_corner,
        )
        outer_path.closeSubpath()

        lip_gradient = QLinearGradient(left_corner, QPointF(right_corner.x(), bottom_ctrl_y))
        lip_gradient.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 165))
        lip_gradient.setColorAt(0.45, QColor(120, 30, 90, 235))
        lip_gradient.setColorAt(1.0, QColor(200, 60, 140, 210))

        painter.setBrush(lip_gradient)
        painter.setPen(QPen(QColor(255, 255, 255, 85), max(1.8, mouth_width * 0.012)))
        painter.drawPath(outer_path)

        if mouth_open > 0.02:
            inner_margin = mouth_width * 0.1
            inner_top_lift = mouth_height * (0.12 + max(0.0, mouth_curve) * 0.25)
            inner_bottom_depth = mouth_height * (0.5 + mouth_open * 1.2)

            inner_left = QPointF(left_corner.x() + inner_margin, base_y - inner_top_lift * 0.4)
            inner_right = QPointF(right_corner.x() - inner_margin, base_y - inner_top_lift * 0.4)

            cavity_top_y = base_y - inner_top_lift
            cavity_bottom_y = base_y + inner_bottom_depth

            inner_path = QPainterPath(inner_left)
            inner_path.cubicTo(
                QPointF(inner_left.x() + mouth_width * 0.18, cavity_top_y),
                QPointF(inner_right.x() - mouth_width * 0.18, cavity_top_y),
                inner_right,
            )
            inner_path.cubicTo(
                QPointF(inner_right.x() - mouth_width * 0.16, cavity_bottom_y),
                QPointF(inner_left.x() + mouth_width * 0.16, cavity_bottom_y),
                inner_left,
            )
            inner_path.closeSubpath()

            inner_gradient = QLinearGradient(
                QPointF(inner_left.x(), cavity_top_y), QPointF(inner_right.x(), cavity_bottom_y)
            )
            inner_gradient.setColorAt(0.0, QColor(255, 210, 230, 70))
            inner_gradient.setColorAt(0.4, QColor(90, 20, 70, 235))
            inner_gradient.setColorAt(1.0, QColor(25, 8, 25, 255))

            painter.setBrush(inner_gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(inner_path)

            if mouth_open > 0.12:
                painter.save()
                painter.setClipPath(inner_path)

                tongue_width = mouth_width * 0.6
                tongue_height = mouth_height * (0.28 + mouth_open * 0.6)
                tongue_rect = QRectF(
                    center.x() - tongue_width * 0.5 + mouth_center_offset,
                    base_y + mouth_height * 0.12,
                    tongue_width,
                    tongue_height,
                )

                tongue_path = QPainterPath()
                tongue_path.addRoundedRect(tongue_rect, tongue_height * 0.6, tongue_height * 0.6)

                tongue_gradient = QLinearGradient(tongue_rect.topLeft(), tongue_rect.bottomLeft())
                tongue_gradient.setColorAt(0.0, QColor(255, 160, 190, 230))
                tongue_gradient.setColorAt(1.0, QColor(210, 70, 120, 235))

                painter.setBrush(tongue_gradient)
                painter.setPen(QPen(QColor(255, 120, 180, 110), max(1.2, mouth_width * 0.008)))
                painter.drawPath(tongue_path)
                painter.restore()

            highlight_path = QPainterPath()
            highlight_start = QPointF(left_corner.x() + mouth_width * 0.2, top_ctrl_y + mouth_height * 0.18)
            highlight_end = QPointF(right_corner.x() - mouth_width * 0.2, top_ctrl_y + mouth_height * 0.18)
            highlight_path.moveTo(highlight_start)
            highlight_path.cubicTo(
                QPointF(highlight_start.x() + mouth_width * 0.14, top_ctrl_y + mouth_height * 0.09),
                QPointF(highlight_end.x() - mouth_width * 0.14, top_ctrl_y + mouth_height * 0.09),
                highlight_end,
            )

            painter.setPen(QPen(QColor(255, 255, 255, 120), mouth_height * 0.085))
            painter.drawPath(highlight_path)

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
            "accent_color": QColor(*preset.accent_color),
        }
