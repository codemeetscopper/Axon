from __future__ import annotations
import time
from dataclasses import dataclass

import board
import busio
from adafruit_pca9685 import PCA9685


@dataclass
class ServoCalibration:
    min_us: int = 500
    max_us: int = 2500


class PanTiltController:
    def __init__(
        self,
        i2c_address: int = 0x40,
        frequency_hz: int = 50,
        pan_channel: int = 0,
        tilt_channel: int = 1,
        pan_cal: ServoCalibration = ServoCalibration(500, 2500),
        tilt_cal: ServoCalibration = ServoCalibration(500, 2500),
        invert_pan: bool = False,
        invert_tilt: bool = False,
    ) -> None:
        self.pan_channel = pan_channel
        self.tilt_channel = tilt_channel
        self.pan_cal = pan_cal
        self.tilt_cal = tilt_cal
        self.invert_pan = invert_pan
        self.invert_tilt = invert_tilt

        self._i2c = busio.I2C(board.SCL, board.SDA)
        self._pca = PCA9685(self._i2c, address=i2c_address)
        self._pca.frequency = frequency_hz

        self._pan_angle = 90.0
        self._tilt_angle = 70.0

    def close(self) -> None:
        try:
            self._pca.deinit()
        except Exception:
            pass

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    @staticmethod
    def _angle_to_duty(angle: float, cal: ServoCalibration) -> int:
        # 50Hz => 20,000 µs period
        angle = PanTiltController._clamp(angle, 0.0, 180.0)
        pulse_us = cal.min_us + (angle / 180.0) * (cal.max_us - cal.min_us)
        duty = int((pulse_us / 20000.0) * 0xFFFF)
        return int(PanTiltController._clamp(duty, 0, 0xFFFF))

    def _write(self, channel: int, angle: float, cal: ServoCalibration) -> None:
        self._pca.channels[channel].duty_cycle = self._angle_to_duty(angle, cal)

    def set_angles(self, pan: float, tilt: float, smooth: bool = True, step_deg: float = 2.0, step_delay: float = 0.01) -> None:
        if self.invert_pan:
            pan = 180.0 - pan
        if self.invert_tilt:
            tilt = 180.0 - tilt

        pan = self._clamp(pan, 0.0, 180.0)
        tilt = self._clamp(tilt, 0.0, 180.0)

        if not smooth:
            self._write(self.pan_channel, pan, self.pan_cal)
            self._write(self.tilt_channel, tilt, self.tilt_cal)
            self._pan_angle, self._tilt_angle = pan, tilt
            return

        cur_pan, cur_tilt = self._pan_angle, self._tilt_angle
        max_delta = max(abs(pan - cur_pan), abs(tilt - cur_tilt))
        steps = max(1, int(max_delta / max(step_deg, 0.1)))

        for i in range(1, steps + 1):
            p = cur_pan + (pan - cur_pan) * (i / steps)
            t = cur_tilt + (tilt - cur_tilt) * (i / steps)
            self._write(self.pan_channel, p, self.pan_cal)
            self._write(self.tilt_channel, t, self.tilt_cal)
            time.sleep(step_delay)

        self._pan_angle, self._tilt_angle = pan, tilt

    def disable_outputs(self) -> None:
        self._pca.channels[self.pan_channel].duty_cycle = 0
        self._pca.channels[self.tilt_channel].duty_cycle = 0
