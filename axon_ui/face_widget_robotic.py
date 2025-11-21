from __future__ import annotations

import math
import random
from typing import Dict, Tuple

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QWidget

from axon_ui.emotion_preset import EmotionPreset


class RoboticFaceWidget(QWidget):
    """Animated robotic face widget with emotion and orientation controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(480, 320)

        self._presets: Dict[str, EmotionPreset] = self._build_presets()
        self._default_emotion = "neutral"
        self._current_emotion = self._default_emotion
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
        self._emotion_hold_time = 0.0
        self._battery_voltage: float | None = None
        self._low_battery_forced = False

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
        self._emotion_hold_time = 0.0
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

    def set_battery_voltage(self, voltage: float) -> None:
        """Update battery voltage and enforce default fear when critically low."""
        self._battery_voltage = float(voltage)
        self._enforce_low_battery_face()

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
        self._emotion_hold_time += dt
        self._enforce_low_battery_face()

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
    # Drawing (Cyberpunk / HUD Style)
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()
        
        # 1. Background: Deep digital void with grid
        self._draw_grid_background(painter, rect)

        face_margin = min(rect.width(), rect.height()) * 0.05
        face_rect = QRectF(
            rect.left() + face_margin,
            rect.top() + face_margin,
            rect.width() - face_margin * 2,
            rect.height() - face_margin * 2,
        )

        center = face_rect.center()
        head_size = min(face_rect.width(), face_rect.height()) * 0.95
        
        # Adjust face rect to be square-ish for the head
        face_rect = QRectF(
            center.x() - head_size * 0.5,
            center.y() - head_size * 0.5,
            head_size,
            head_size,
        )
        center = face_rect.center()

        painter.save()
        painter.translate(center)
        painter.rotate(self._orientation["roll"])
        painter.translate(-center)

        # 2. Head Outline: Glowing HUD frame
        self._draw_hud_head_frame(painter, face_rect)

        accent_color: QColor = self._state["accent_color"]
        
        # Calculate positions
        eye_height = face_rect.height() * 0.22
        eye_width = face_rect.width() * 0.24
        eye_spacing = face_rect.width() * 0.20

        yaw_offset = self._orientation["yaw"] / 45.0
        pitch_offset = self._orientation["pitch"] / 45.0
        eye_center_offset_x = yaw_offset * face_rect.width() * 0.08

        left_eye_center = QPointF(
            center.x() - eye_spacing + eye_center_offset_x,
            center.y() - face_rect.height() * 0.1 + pitch_offset * 20.0,
        )
        right_eye_center = QPointF(
            center.x() + eye_spacing + eye_center_offset_x,
            center.y() - face_rect.height() * 0.1 + pitch_offset * 20.0,
        )

        # Blink logic
        eye_openness = max(0.05, min(1.3, self._state["eye_openness"]))
        blink_factor = 1.0
        if self._blinking:
            blink_factor -= math.sin(min(1.0, self._blink_phase) * math.pi)
            blink_factor = max(0.0, blink_factor)
        effective_openness = max(0.0, eye_openness * blink_factor)

        # 3. Eyes: Digital Apertures
        for eye_center, direction in ((left_eye_center, -1), (right_eye_center, 1)):
            self._draw_digital_eye(
                painter,
                eye_center,
                eye_width,
                eye_height,
                effective_openness,
                self._state["eye_curve"] * direction,
                self._state["iris_size"],
                accent_color,
                direction
            )

        # 4. Brows: Floating Neon Bars
        self._draw_hud_brows(
            painter, 
            left_eye_center, 
            right_eye_center, 
            eye_width, 
            self._state["brow_raise"], 
            self._state["brow_tilt"], 
            accent_color
        )

        # 5. Mouth: Oscilloscope / Waveform
        self._draw_oscilloscope_mouth(painter, center, face_rect, accent_color)

        # 6. Emotion Icons: Holographic projections
        self._draw_holographic_icon(painter, face_rect, accent_color)

        painter.restore()

    # ------------------------------------------------------------------
    # Cyberpunk Drawing Helpers
    # ------------------------------------------------------------------
    def _draw_grid_background(self, painter: QPainter, rect: QRectF) -> None:
        # Deep void background
        bg_gradient = QLinearGradient(0, 0, 0, rect.height())
        bg_gradient.setColorAt(0.0, QColor(5, 5, 10))
        bg_gradient.setColorAt(1.0, QColor(0, 0, 5))
        painter.fillRect(rect, bg_gradient)

        # Grid lines
        painter.save()
        grid_pen = QPen(QColor(0, 255, 255, 15))
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        
        step = 40
        # Vertical lines
        x = rect.left()
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        
        # Horizontal lines (perspective effect approx)
        y = rect.top()
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
            
        # Scanning line
        scan_y = (self._time * 100) % (rect.height() + 100) - 50
        scan_grad = QLinearGradient(0, scan_y, 0, scan_y + 50)
        scan_grad.setColorAt(0.0, QColor(0, 255, 255, 0))
        scan_grad.setColorAt(0.5, QColor(0, 255, 255, 30))
        scan_grad.setColorAt(1.0, QColor(0, 255, 255, 0))
        painter.fillRect(rect, scan_grad)
        
        painter.restore()

    def _draw_hud_head_frame(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        
        # Glowing hex frame
        pen = QPen(QColor(0, 200, 255, 100))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Main circle/hex approximation
        path = QPainterPath()
        w, h = rect.width(), rect.height()
        
        # Top bracket
        path.moveTo(rect.left() + w*0.3, rect.top())
        path.lineTo(rect.right() - w*0.3, rect.top())
        path.lineTo(rect.right(), rect.top() + h*0.2)
        
        # Bottom bracket
        path.moveTo(rect.right() - w*0.3, rect.bottom())
        path.lineTo(rect.left() + w*0.3, rect.bottom())
        path.lineTo(rect.left(), rect.bottom() - h*0.2)
        
        # Side accents
        path.moveTo(rect.left(), rect.top() + h*0.3)
        path.lineTo(rect.left(), rect.top() + h*0.7)
        
        path.moveTo(rect.right(), rect.top() + h*0.3)
        path.lineTo(rect.right(), rect.top() + h*0.7)
        
        painter.drawPath(path)
        
        # Decorative data bits
        painter.setPen(QPen(QColor(0, 255, 255, 180), 1.0))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(QPointF(rect.right() - 60, rect.top() + 20), f"SYS.VOLT: {self._battery_voltage or 12.4:.1f}V")
        painter.drawText(QPointF(rect.left() + 10, rect.bottom() - 10), f"EMO: {self._current_emotion.upper()}")
        
        painter.restore()

    def _draw_digital_eye(
        self,
        painter: QPainter,
        center: QPointF,
        width: float,
        height: float,
        openness: float,
        curve: float,
        iris_scale: float,
        accent: QColor,
        direction: int
    ) -> None:
        painter.save()
        
        # Dynamic scaling for blink
        scaled_height = height * openness
        if scaled_height < 2.0: 
            # Fully closed line
            painter.setPen(QPen(accent, 2.0))
            painter.drawLine(center.x() - width*0.5, center.y(), center.x() + width*0.5, center.y())
            painter.restore()
            return

        eye_rect = QRectF(
            center.x() - width * 0.5,
            center.y() - scaled_height * 0.5,
            width,
            scaled_height,
        )

        # Rotate for expression
        painter.translate(center)
        painter.rotate(curve * 15.0)
        painter.translate(-center)

        # 1. Outer Aperture Ring (segmented)
        pen = QPen(accent)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        segment_angle = 60
        for i in range(0, 360, segment_angle + 10):
            painter.drawArc(eye_rect, i * 16, segment_angle * 16)

        # 2. Iris (Digital Core)
        iris_radius = min(width, scaled_height) * 0.35 * iris_scale
        iris_rect = QRectF(
            center.x() - iris_radius,
            center.y() - iris_radius,
            iris_radius * 2,
            iris_radius * 2
        )
        
        # Glowing core
        glow = QRadialGradient(center, iris_radius)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 255))
        glow.setColorAt(0.7, QColor(accent.red(), accent.green(), accent.blue(), 100))
        glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(iris_rect)
        
        # Crosshair in pupil
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        cross_size = iris_radius * 0.6
        painter.drawLine(QPointF(center.x() - cross_size, center.y()), QPointF(center.x() + cross_size, center.y()))
        painter.drawLine(QPointF(center.x(), center.y() - cross_size), QPointF(center.x(), center.y() + cross_size))

        # 3. Scan lines inside eye
        painter.setClipRect(eye_rect)
        scan_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 50))
        scan_pen.setWidthF(1.0)
        painter.setPen(scan_pen)
        for y in range(int(eye_rect.top()), int(eye_rect.bottom()), 4):
            painter.drawLine(QPointF(eye_rect.left(), y), QPointF(eye_rect.right(), y))

        painter.restore()

    def _draw_hud_brows(
        self,
        painter: QPainter,
        left_center: QPointF,
        right_center: QPointF,
        eye_width: float,
        raise_amount: float,
        tilt: float,
        accent: QColor,
    ) -> None:
        brow_width = eye_width * 1.2
        offset_y = -eye_width * (0.6 + raise_amount * 0.4)

        painter.save()
        pen = QPen(accent)
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        for center, direction in ((left_center, -1), (right_center, 1)):
            # Calculate position
            bx = center.x()
            by = center.y() + offset_y
            
            painter.save()
            painter.translate(bx, by)
            painter.rotate(tilt * 25.0 * direction)
            
            # Draw segmented brow
            # Main bar
            painter.drawLine(QPointF(-brow_width*0.5, 0), QPointF(brow_width*0.5, 0))
            
            # Accent bit above
            painter.setPen(QPen(accent.lighter(150), 1.5))
            painter.drawLine(QPointF(-brow_width*0.3, -6), QPointF(brow_width*0.3, -6))
            
            painter.restore()

        painter.restore()

    def _draw_oscilloscope_mouth(self, painter: QPainter, center: QPointF, face_rect: QRectF, accent: QColor) -> None:
        painter.save()
        
        # Mouth parameters
        width = face_rect.width() * 0.4 * self._state["mouth_width"]
        height = face_rect.height() * 0.15 * self._state["mouth_open"]
        curve = self._state["mouth_curve"]
        
        yaw_offset = self._orientation["yaw"] / 45.0
        mouth_center_x = center.x() + yaw_offset * face_rect.width() * 0.05
        mouth_center_y = center.y() + face_rect.height() * 0.25
        
        # Draw the "Voice Line"
        path = QPainterPath()
        steps = 20
        step_x = width / steps
        start_x = mouth_center_x - width * 0.5
        
        path.moveTo(start_x, mouth_center_y)
        
        # Generate waveform based on emotion/state
        # If speaking (mouth open), add noise. If smiling, curve up.
        
        amplitude = height * 0.5
        if amplitude < 2.0: amplitude = 2.0 # Minimum line thickness visual
        
        for i in range(steps + 1):
            x = start_x + i * step_x
            # Normalized x from -1 to 1
            nx = (i / steps) * 2.0 - 1.0
            
            # Base curve (smile/frown)
            # Parabola: y = x^2
            curve_y = nx * nx * curve * -20.0 
            
            # Noise/Voice modulation
            noise = 0.0
            if self._state["mouth_open"] > 0.1:
                noise = random.uniform(-1.0, 1.0) * amplitude * (1.0 - abs(nx)) # Taper noise at ends
            
            path.lineTo(x, mouth_center_y + curve_y + noise)
            
        # Glow effect
        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 100), 4.0))
        painter.drawPath(path)
        
        painter.setPen(QPen(accent, 2.0))
        painter.drawPath(path)
        
        painter.restore()

    def _draw_holographic_icon(self, painter: QPainter, face_rect: QRectF, accent: QColor) -> None:
        emotion = self._current_emotion
        if emotion == "neutral" or self._emotion_hold_time < 0.5:
            return

        painter.save()
        
        # Position icon near cheek or forehead
        icon_pos = QPointF(face_rect.right() - face_rect.width()*0.2, face_rect.top() + face_rect.height()*0.2)
        size = face_rect.width() * 0.15
        
        # Bobbing animation
        bobble = math.sin(self._time * 4.0) * 5.0
        icon_pos.setY(icon_pos.y() + bobble)
        
        painter.translate(icon_pos)
        
        # Glitch effect occasionally
        if random.random() < 0.05:
            painter.translate(random.uniform(-2, 2), random.uniform(-2, 2))

        pen = QPen(accent)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        if emotion == "happy":
            # Digital Heart
            path = QPainterPath()
            path.moveTo(0, size*0.3)
            path.lineTo(size*0.5, -size*0.5)
            path.lineTo(0, -size*0.2)
            path.lineTo(-size*0.5, -size*0.5)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawText(QPointF(-10, size*0.6), "^_^")
            
        elif emotion == "sad":
            # Rain/Tear
            painter.drawLine(0, -size*0.5, 0, size*0.5)
            painter.drawLine(-5, 0, 5, 0)
            painter.drawText(QPointF(-15, size*0.8), "ERR:SAD")
            
        elif emotion == "angry":
            # Warning Hex
            painter.drawRect(QRectF(-size*0.4, -size*0.4, size*0.8, size*0.8))
            painter.drawLine(-size*0.4, -size*0.4, size*0.4, size*0.4)
            painter.drawLine(-size*0.4, size*0.4, size*0.4, -size*0.4)
            
        elif emotion == "surprised":
            # Exclamation
            painter.drawEllipse(QPointF(0, -size*0.2), size*0.1, size*0.4)
            painter.drawEllipse(QPointF(0, size*0.4), size*0.1, size*0.1)
            
        elif emotion == "sleepy":
            painter.setFont(QFont("Consolas", 14))
            painter.drawText(QPointF(0, 0), "Zzz...")
            
        elif emotion == "love":
             painter.drawText(QPointF(-10, 0), "<3")
             
        elif emotion == "fearful":
            painter.drawText(QPointF(-20, 0), "WARN!!")
            
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

    def _enforce_low_battery_face(self) -> None:
        """Force fearful face when battery is critically low."""
        if self._battery_voltage is None:
            return
        low_battery = self._battery_voltage < 10.0
        if low_battery and not self._low_battery_forced:
            self._low_battery_forced = True
            if self._current_emotion != "fearful":
                self.set_emotion("fearful")
        elif not low_battery and self._low_battery_forced:
            self._low_battery_forced = False
            if self._current_emotion == "fearful":
                self.set_emotion(self._default_emotion)
