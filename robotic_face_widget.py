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
        head_size = min(face_rect.width(), face_rect.height()) * 1.0
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
        # painter.setPen(QPen(QColor(110, 140, 220, 140), face_rect.width() * 0.012))
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
        width_factor = 0.42 * self._state["mouth_width"]
        height_factor = 0.08 * self._state["mouth_height"]
        openness_factor = 0.06 * self._state["mouth_open"]
        smile_factor = self._state["mouth_curve"]

        yaw_offset = self._orientation["yaw"] / 45.0
        mouth_center_offset = yaw_offset * face_rect.width() * 0.05

        mouth_center = QPointF(
            center.x() + mouth_center_offset,
            center.y() + face_rect.height() * 0.26 + self._breathe_offset * 0.12 - face_rect.height() * 0.035 * smile_factor,
        )

        mouth_width = face_rect.width() * width_factor
        mouth_height = face_rect.height() * height_factor

        horizontal_margin = face_rect.width() * 0.08
        vertical_margin = face_rect.height() * 0.1
        max_center_x = face_rect.right() - horizontal_margin - mouth_width * 0.5
        min_center_x = face_rect.left() + horizontal_margin + mouth_width * 0.5
        mouth_center.setX(max(min_center_x, min(max_center_x, mouth_center.x())))

        max_center_y = face_rect.bottom() - vertical_margin - mouth_height
        min_center_y = center.y() + face_rect.height() * 0.05
        mouth_center.setY(max(min_center_y, min(max_center_y, mouth_center.y())))

        half_width = mouth_width * 0.5
        control_offset = mouth_height * 1.6
        open_amount = face_rect.height() * openness_factor
        lip_volume = face_rect.height() * (0.018 + abs(smile_factor) * 0.012 + openness_factor * 0.45)
        corner_lift = control_offset * 0.55 * smile_factor

        left_corner = QPointF(mouth_center.x() - half_width, mouth_center.y() - corner_lift)
        right_corner = QPointF(mouth_center.x() + half_width, mouth_center.y() - corner_lift)

        upper_mid_y = mouth_center.y() - control_offset * smile_factor * 0.9 - lip_volume * 0.15
        lower_mid_y = mouth_center.y() + lip_volume + open_amount * 0.8 + control_offset * max(0.0, -smile_factor) * 0.5

        lower_drop = lip_volume + open_amount * 0.6 + control_offset * max(0.0, -smile_factor) * 0.4

        lip_path = QPainterPath(left_corner)
        lip_path.cubicTo(
            QPointF(left_corner.x() + half_width * 0.35, left_corner.y() - control_offset * (0.6 * smile_factor + 0.2)),
            QPointF(mouth_center.x() - half_width * 0.1, upper_mid_y),
            QPointF(mouth_center.x(), upper_mid_y),
        )
        lip_path.cubicTo(
            QPointF(mouth_center.x() + half_width * 0.1, upper_mid_y),
            QPointF(right_corner.x() - half_width * 0.35, right_corner.y() - control_offset * (0.6 * smile_factor + 0.2)),
            right_corner,
        )
        lip_path.cubicTo(
            QPointF(right_corner.x() - half_width * 0.25, right_corner.y() + lower_drop),
            QPointF(mouth_center.x() + half_width * 0.12, lower_mid_y),
            QPointF(mouth_center.x(), lower_mid_y),
        )
        lip_path.cubicTo(
            QPointF(mouth_center.x() - half_width * 0.12, lower_mid_y),
            QPointF(left_corner.x() + half_width * 0.25, left_corner.y() + lower_drop),
            left_corner,
        )
        lip_path.closeSubpath()

        painter.save()

        if open_amount > face_rect.height() * 0.006:
            inner_left = left_corner.x() + face_rect.width() * 0.06
            inner_right = right_corner.x() - face_rect.width() * 0.06
            cavity_top = mouth_center.y() - lip_volume * 0.15 - control_offset * smile_factor * 0.2
            cavity_bottom = cavity_top + open_amount + lip_volume * 0.65

            mouth_open_path = QPainterPath(QPointF(inner_left, cavity_top))
            mouth_open_path.quadTo(
                QPointF(mouth_center.x(), cavity_top - control_offset * smile_factor * 0.4),
                QPointF(inner_right, cavity_top),
            )
            mouth_open_path.quadTo(
                QPointF(mouth_center.x(), cavity_bottom + lip_volume * 0.2),
                QPointF(inner_left, cavity_bottom),
            )
            mouth_open_path.closeSubpath()

            cavity_gradient = QLinearGradient(mouth_center.x(), cavity_top, mouth_center.x(), cavity_bottom)
            cavity_gradient.setColorAt(0.0, QColor(35, 20, 45, 230))
            cavity_gradient.setColorAt(1.0, QColor(10, 6, 18, 240))

            painter.setBrush(cavity_gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(mouth_open_path)

            if open_amount > face_rect.height() * 0.045:
                teeth_height = min(face_rect.height() * 0.05 + open_amount * 0.15, (cavity_bottom - cavity_top) * 0.6)
                teeth_rect = QRectF(
                    mouth_center.x() - mouth_width * 0.32,
                    cavity_top + teeth_height * 0.15,
                    mouth_width * 0.64,
                    teeth_height,
                )
                teeth_path = QPainterPath()
                teeth_path.addRoundedRect(teeth_rect, teeth_height * 0.4, teeth_height * 0.4)
                painter.setBrush(QColor(240, 242, 255, 220))
                painter.drawPath(teeth_path)

        lip_top_highlight = QPainterPath(left_corner)
        lip_top_highlight.cubicTo(
            QPointF(left_corner.x() + half_width * 0.35, left_corner.y() - control_offset * (0.6 * smile_factor + 0.2)),
            QPointF(mouth_center.x() - half_width * 0.1, upper_mid_y - lip_volume * 0.1),
            QPointF(mouth_center.x(), upper_mid_y - lip_volume * 0.1),
        )
        lip_top_highlight.cubicTo(
            QPointF(mouth_center.x() + half_width * 0.1, upper_mid_y - lip_volume * 0.1),
            QPointF(right_corner.x() - half_width * 0.35, right_corner.y() - control_offset * (0.6 * smile_factor + 0.2)),
            right_corner,
        )

        lip_gradient = QLinearGradient(left_corner, QPointF(left_corner.x(), lower_mid_y))
        lip_gradient.setColorAt(
            0.0,
            QColor(
                int(accent.red() * 0.4 + 150),
                int(accent.green() * 0.35 + 120),
                int(accent.blue() * 0.35 + 140),
                235,
            ),
        )
        lip_gradient.setColorAt(
            1.0,
            QColor(
                int(accent.red() * 0.3 + 70),
                int(accent.green() * 0.3 + 60),
                int(accent.blue() * 0.3 + 80),
                245,
            ),
        )

        outline_color = QColor(
            int(accent.red() * 0.7 + 60),
            int(accent.green() * 0.7 + 60),
            int(accent.blue() * 0.7 + 90),
            230,
        )

        painter.setBrush(lip_gradient)
        painter.setPen(QPen(outline_color, max(1.6, face_rect.width() * 0.004), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(lip_path)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 130), max(1.0, face_rect.width() * 0.003)))
        painter.drawPath(lip_top_highlight)

        painter.restore()

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
