from __future__ import annotations

import math
import random
from typing import Dict, Tuple

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from axon_ui.emotion_preset import EmotionPreset


class RoboticFaceWidget(QWidget):
    """Animated robotic face widget with emotion and orientation controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(480, 320)

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

        face_margin = min(rect.width(), rect.height()) * 0.035
        face_rect = QRectF(
            rect.left() + face_margin,
            rect.top() + face_margin,
            rect.width() - face_margin * 2,
            rect.height() - face_margin * 2,
        )

        center = face_rect.center()
        head_size = min(face_rect.width(), face_rect.height()) * 1.2
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
        # head_path.addEllipse(face_rect)
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

        pen_color = QColor(
            int(accent.red() * 0.75 + 35),
            int(accent.green() * 0.75 + 35),
            int(accent.blue() * 0.75 + 45),
        )
        stroke_width = max(1.8, face_rect.width() * 0.0045)

        emotion = self._current_emotion

        if emotion == "neutral":
            self._draw_mouth_neutral(painter, mouth_center, face_rect, pen_color, stroke_width)
            return

        if emotion == "happy":
            self._draw_mouth_happy(painter, mouth_center, face_rect, accent, pen_color, stroke_width)
            return

        if emotion == "surprised":
            self._draw_mouth_surprised(painter, mouth_center, face_rect, accent, pen_color, stroke_width)
            return

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
        control_offset = mouth_height * 1.45
        open_amount = face_rect.height() * openness_factor

        corner_lift = control_offset * 0.35 * smile_factor
        left_corner = QPointF(mouth_center.x() - half_width, mouth_center.y() - corner_lift)
        right_corner = QPointF(mouth_center.x() + half_width, mouth_center.y() - corner_lift)

        top_control = QPointF(mouth_center.x(), mouth_center.y() - control_offset * smile_factor)

        lower_corner_bias = control_offset * 0.18 * smile_factor
        lower_left = QPointF(left_corner.x(), mouth_center.y() + open_amount + lower_corner_bias)
        lower_right = QPointF(right_corner.x(), mouth_center.y() + open_amount + lower_corner_bias)

        bottom_control = QPointF(
            mouth_center.x(),
            mouth_center.y() + open_amount + control_offset * (0.28 + max(0.0, -smile_factor) * 0.45),
        )

        top_path = QPainterPath(left_corner)
        top_path.quadTo(top_control, right_corner)

        painter.save()

        side_threshold = face_rect.height() * 0.003
        if open_amount > side_threshold:
            fill_path = QPainterPath(left_corner)
            fill_path.quadTo(top_control, right_corner)
            fill_path.lineTo(lower_right)
            fill_path.quadTo(bottom_control, lower_left)
            fill_path.closeSubpath()

            fill_color = QColor(
                int(accent.red() * 0.6 + 50),
                int(accent.green() * 0.55 + 45),
                int(accent.blue() * 0.55 + 55),
                140,
            )
            painter.setBrush(fill_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(fill_path)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(pen_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(top_path)

        if open_amount > side_threshold:
            lower_path = QPainterPath(lower_left)
            lower_path.quadTo(bottom_control, lower_right)
            subtle_pen = QPen(pen_color.lighter(120), stroke_width * 0.85, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(subtle_pen)
            painter.drawPath(lower_path)

            side_pen = QPen(pen_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(side_pen)

            left_side = QPainterPath(left_corner)
            left_side.quadTo(
                QPointF(
                    left_corner.x() - face_rect.width() * 0.01,
                    (left_corner.y() + lower_left.y()) * 0.5 + face_rect.height() * 0.01,
                ),
                lower_left,
            )
            painter.drawPath(left_side)

            right_side = QPainterPath(right_corner)
            right_side.quadTo(
                QPointF(
                    right_corner.x() + face_rect.width() * 0.01,
                    (right_corner.y() + lower_right.y()) * 0.5 + face_rect.height() * 0.01,
                ),
                lower_right,
            )
            painter.drawPath(right_side)

        painter.restore()

    def _draw_mouth_neutral(
        self,
        painter: QPainter,
        mouth_center: QPointF,
        face_rect: QRectF,
        pen_color: QColor,
        stroke_width: float,
    ) -> None:
        painter.save()

        adjusted_center = QPointF(mouth_center)
        rect_width = face_rect.width() * 0.46 * self._state["mouth_width"]
        rect_height = max(12.0, min(18.0, face_rect.height() * 0.03))

        horizontal_margin = face_rect.width() * 0.08
        vertical_margin = face_rect.height() * 0.1
        max_center_x = face_rect.right() - horizontal_margin - rect_width * 0.5
        min_center_x = face_rect.left() + horizontal_margin + rect_width * 0.5
        adjusted_center.setX(max(min_center_x, min(max_center_x, adjusted_center.x())))

        face_center_y = face_rect.center().y()
        max_center_y = face_rect.bottom() - vertical_margin - rect_height * 0.5
        min_center_y = face_center_y + face_rect.height() * 0.05
        adjusted_center.setY(max(min_center_y, min(max_center_y, adjusted_center.y())))

        rect = QRectF(
            adjusted_center.x() - rect_width * 0.5,
            adjusted_center.y() - rect_height * 0.5,
            rect_width,
            rect_height,
        )

        fill_color = QColor(
            int(pen_color.red() * 0.8 + 25),
            int(pen_color.green() * 0.8 + 25),
            int(pen_color.blue() * 0.8 + 25),
            150,
        )

        painter.setBrush(fill_color)
        painter.setPen(QPen(pen_color, stroke_width * 0.85, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawRect(rect)
        painter.restore()

    def _draw_mouth_happy(
        self,
        painter: QPainter,
        mouth_center: QPointF,
        face_rect: QRectF,
        accent: QColor,
        pen_color: QColor,
        stroke_width: float,
    ) -> None:
        painter.save()

        adjusted_center = QPointF(mouth_center)
        mouth_width = face_rect.width() * 0.46 * self._state["mouth_width"]
        smile_height = face_rect.height() * 0.11
        thickness = max(10.0, face_rect.height() * 0.035)

        horizontal_margin = face_rect.width() * 0.08
        max_center_x = face_rect.right() - horizontal_margin - mouth_width * 0.5
        min_center_x = face_rect.left() + horizontal_margin + mouth_width * 0.5
        adjusted_center.setX(max(min_center_x, min(max_center_x, adjusted_center.x())))

        face_center_y = face_rect.center().y()
        vertical_margin = face_rect.height() * 0.1
        max_center_y = face_rect.bottom() - vertical_margin - thickness
        min_center_y = face_center_y + face_rect.height() * 0.04
        adjusted_center.setY(max(min_center_y, min(max_center_y, adjusted_center.y())))

        outer_left = QPointF(adjusted_center.x() - mouth_width * 0.5, adjusted_center.y() - thickness * 0.35)
        outer_right = QPointF(adjusted_center.x() + mouth_width * 0.5, adjusted_center.y() - thickness * 0.35)
        outer_control = QPointF(adjusted_center.x(), adjusted_center.y() + smile_height)

        inner_right = QPointF(adjusted_center.x() + mouth_width * 0.38, adjusted_center.y() + thickness * 0.65)
        inner_left = QPointF(adjusted_center.x() - mouth_width * 0.38, adjusted_center.y() + thickness * 0.65)
        inner_control = QPointF(adjusted_center.x(), adjusted_center.y() + smile_height * 1.08)

        path = QPainterPath(outer_left)
        path.quadTo(outer_control, outer_right)
        path.lineTo(inner_right)
        path.quadTo(inner_control, inner_left)
        path.closeSubpath()

        fill_color = QColor(
            int(accent.red() * 0.6 + 65),
            int(accent.green() * 0.6 + 55),
            int(accent.blue() * 0.6 + 70),
            170,
        )

        painter.setBrush(fill_color)
        painter.setPen(QPen(pen_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawPath(path)
        painter.restore()

    def _draw_mouth_surprised(
        self,
        painter: QPainter,
        mouth_center: QPointF,
        face_rect: QRectF,
        accent: QColor,
        pen_color: QColor,
        stroke_width: float,
    ) -> None:
        painter.save()

        adjusted_center = QPointF(mouth_center)
        base_size = face_rect.width() * 0.22 * self._state["mouth_width"]
        width = max(38.0, base_size)
        height = max(32.0, width * 1.05 * self._state["mouth_height"])

        horizontal_margin = face_rect.width() * 0.08
        vertical_margin = face_rect.height() * 0.1
        max_center_x = face_rect.right() - horizontal_margin - width * 0.5
        min_center_x = face_rect.left() + horizontal_margin + width * 0.5
        adjusted_center.setX(max(min_center_x, min(max_center_x, adjusted_center.x())))

        face_center_y = face_rect.center().y()
        max_center_y = face_rect.bottom() - vertical_margin - height * 0.5
        min_center_y = face_center_y + face_rect.height() * 0.02
        adjusted_center.setY(max(min_center_y, min(max_center_y, adjusted_center.y())))

        rect = QRectF(
            adjusted_center.x() - width * 0.5,
            adjusted_center.y() - height * 0.5,
            width,
            height,
        )

        fill_color = QColor(
            int(accent.red() * 0.6 + 40),
            int(accent.green() * 0.6 + 40),
            int(accent.blue() * 0.6 + 60),
            165,
        )

        painter.setBrush(fill_color)
        painter.setPen(QPen(pen_color, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

        path = QPainterPath()
        path.addEllipse(rect)
        painter.drawPath(path)
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
                mouth_curve=0.0,
                mouth_open=0.05,
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
                mouth_curve=0.0,
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
            "angry": EmotionPreset(
                name="angry",
                eye_openness=0.7,
                eye_curve=-0.55,
                brow_raise=-0.45,
                brow_tilt=0.55,
                mouth_curve=-0.4,
                mouth_open=0.2,
                mouth_width=0.95,
                mouth_height=0.85,
                iris_size=0.92,
                accent_color=(255, 90, 90),
            ),
            "fearful": EmotionPreset(
                name="fearful",
                eye_openness=1.5,
                eye_curve=-0.1,
                brow_raise=0.35,
                brow_tilt=0.25,
                mouth_curve=-0.1,
                mouth_open=0.85,
                mouth_width=0.9,
                mouth_height=1.35,
                iris_size=1.12,
                accent_color=(255, 220, 160),
            ),
            "disgusted": EmotionPreset(
                name="disgusted",
                eye_openness=0.75,
                eye_curve=-0.25,
                brow_raise=-0.35,
                brow_tilt=-0.45,
                mouth_curve=-0.2,
                mouth_open=0.12,
                mouth_width=0.88,
                mouth_height=0.8,
                iris_size=0.9,
                accent_color=(140, 220, 110),
            ),
            "smirk": EmotionPreset(
                name="smirk",
                eye_openness=0.95,
                eye_curve=0.1,
                brow_raise=0.05,
                brow_tilt=0.5,
                mouth_curve=0.55,
                mouth_open=0.12,
                mouth_width=1.02,
                mouth_height=0.95,
                iris_size=1.0,
                accent_color=(255, 170, 200),
            ),
            "proud": EmotionPreset(
                name="proud",
                eye_openness=1.05,
                eye_curve=0.25,
                brow_raise=0.28,
                brow_tilt=-0.15,
                mouth_curve=0.65,
                mouth_open=0.18,
                mouth_width=1.08,
                mouth_height=1.05,
                iris_size=1.02,
                accent_color=(255, 200, 150),
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
