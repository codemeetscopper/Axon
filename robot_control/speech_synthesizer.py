"""Text-to-speech output using espeak-ng via ALSA."""

from __future__ import annotations

import logging
import subprocess

LOGGER = logging.getLogger(__name__)


class SpeechSynthesizer:
    """Blocking TTS using espeak-ng piped to aplay."""

    def __init__(self, rate: int = 145, amplitude: int = 200, voice: str = "en") -> None:
        self._rate = rate
        self._amplitude = amplitude
        self._voice = voice

    def speak(self, text: str) -> None:
        """Speak *text* synchronously (blocks until finished)."""
        LOGGER.info("TTS: %s", text)
        try:
            espeak = subprocess.Popen(
                ["espeak-ng", "-a", str(self._amplitude), "-s", str(self._rate),
                 "-v", self._voice, "--stdout", text],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["aplay", "-D", "plughw:2,0", "-q"],
                stdin=espeak.stdout,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            espeak.wait(timeout=5)
        except Exception:
            LOGGER.exception("TTS playback failed")
