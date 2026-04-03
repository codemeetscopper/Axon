"""Dual-mic speech listener with sound direction detection and Google STT."""

from __future__ import annotations

import io
import logging
import subprocess
import threading
import wave
from typing import Callable, Optional

import numpy as np

LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_DURATION_S = 0.25
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION_S)
CHUNK_BYTES = CHUNK_SAMPLES * 2
SILENCE_THRESHOLD_DEFAULT = 800
SILENCE_CHUNKS_TO_STOP = 6   # ~1.5s silence ends utterance
MIN_SPEECH_CHUNKS = 3
AMBIENT_CALIBRATION_CHUNKS = 20  # 5s of ambient measurement on startup
PRIMARY_MIC = "plughw:2,0"   # USB Audio Device
SECONDARY_MIC = "plughw:3,0" # Camera mic


class SpeechListener:
    """Dual-mic speech capture with direction estimation and Google STT."""

    def __init__(
        self,
        device_index: Optional[int] = None,
        language: str = "en-US",
        alsa_device: str = PRIMARY_MIC,
        alsa_device_secondary: str = SECONDARY_MIC,
    ) -> None:
        self._language = language
        self._alsa_device = alsa_device
        self._alsa_device_secondary = alsa_device_secondary

        self._threshold = SILENCE_THRESHOLD_DEFAULT
        self._stop_event = threading.Event()
        self._muted = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._listeners_lock = threading.Lock()
        self._transcript_consumers: list[Callable[[str], None]] = []
        self._direction_consumers: list[Callable[[float], None]] = []

        # Secondary mic state
        self._sec_proc: Optional[subprocess.Popen] = None
        self._sec_rms: float = 0.0
        self._sec_lock = threading.Lock()
        self._sec_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._muted.clear()
        self._thread = threading.Thread(
            target=self._run, name="SpeechListener", daemon=True,
        )
        self._thread.start()
        LOGGER.info("Speech listener started (primary=%s)", self._alsa_device)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        if self._sec_proc:
            self._sec_proc.terminate()
        LOGGER.info("Speech listener stopped")

    def mute(self) -> None:
        self._muted.set()

    def unmute(self) -> None:
        self._muted.clear()

    # ------------------------------------------------------------------
    # Consumer registration
    # ------------------------------------------------------------------
    def add_transcript_consumer(self, consumer: Callable[[str], None]) -> None:
        with self._listeners_lock:
            self._transcript_consumers.append(consumer)

    def remove_transcript_consumer(self, consumer: Callable[[str], None]) -> None:
        with self._listeners_lock:
            if consumer in self._transcript_consumers:
                self._transcript_consumers.remove(consumer)

    def add_direction_consumer(self, consumer: Callable[[float], None]) -> None:
        """Register callback for sound direction. Value: -1.0 (left) to 1.0 (right)."""
        with self._listeners_lock:
            self._direction_consumers.append(consumer)

    # ------------------------------------------------------------------
    # Internal — primary mic
    # ------------------------------------------------------------------
    def _run(self) -> None:
        import speech_recognition as sr
        recognizer = sr.Recognizer()

        proc = subprocess.Popen(
            ["arecord", "-D", self._alsa_device, "-f", "S16_LE",
             "-r", str(SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        LOGGER.info("Primary mic open: %s @ %dHz", self._alsa_device, SAMPLE_RATE)

        # Calibrate ambient noise level
        self._threshold = SILENCE_THRESHOLD_DEFAULT
        rms_values = []
        for _ in range(AMBIENT_CALIBRATION_CHUNKS):
            chunk = proc.stdout.read(CHUNK_BYTES)
            if chunk and len(chunk) == CHUNK_BYTES:
                rms_values.append(self._rms(chunk))
        if rms_values:
            ambient = float(np.mean(rms_values))
            self._threshold = max(SILENCE_THRESHOLD_DEFAULT, ambient * 3.0)
            LOGGER.info("Ambient RMS=%.0f, speech threshold=%.0f", ambient, self._threshold)

        # Start secondary mic reader
        self._start_secondary_mic()

        try:
            while not self._stop_event.is_set():
                self._listen_loop(proc, recognizer, sr)
        finally:
            proc.terminate()
            proc.wait(timeout=2)

    def _listen_loop(self, proc, recognizer, sr) -> None:
        speech_chunks: list[bytes] = []
        silence_count = 0
        in_speech = False

        while not self._stop_event.is_set():
            chunk = proc.stdout.read(CHUNK_BYTES)
            if not chunk or len(chunk) < CHUNK_BYTES:
                break

            if self._muted.is_set():
                in_speech = False
                speech_chunks.clear()
                silence_count = 0
                continue

            rms = self._rms(chunk)

            if rms > self._threshold:
                if not in_speech:
                    LOGGER.info("Speech start (RMS=%.0f)", rms)
                    self._estimate_direction(rms)
                speech_chunks.append(chunk)
                silence_count = 0
                in_speech = True
            elif in_speech:
                speech_chunks.append(chunk)
                silence_count += 1
                if silence_count >= SILENCE_CHUNKS_TO_STOP:
                    if len(speech_chunks) >= MIN_SPEECH_CHUNKS:
                        self._recognise(speech_chunks, recognizer, sr)
                    speech_chunks.clear()
                    silence_count = 0
                    in_speech = False
                    return

    def _recognise(self, chunks: list[bytes], recognizer, sr) -> None:
        audio_bytes = b"".join(chunks)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_bytes)
        buf.seek(0)
        with sr.AudioFile(buf) as source:
            audio = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio, language=self._language).strip()
            if text:
                LOGGER.info("Heard: %s", text)
                self._dispatch(text)
        except sr.UnknownValueError:
            LOGGER.debug("Google STT: could not understand audio")
        except sr.RequestError as exc:
            LOGGER.warning("Google STT request failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal — secondary mic for direction
    # ------------------------------------------------------------------
    def _start_secondary_mic(self) -> None:
        try:
            self._sec_proc = subprocess.Popen(
                ["arecord", "-D", self._alsa_device_secondary, "-f", "S16_LE",
                 "-r", str(SAMPLE_RATE), "-c", "1", "-t", "raw", "-q"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self._sec_thread = threading.Thread(
                target=self._secondary_loop, name="SecondaryMic", daemon=True,
            )
            self._sec_thread.start()
            LOGGER.info("Secondary mic open: %s", self._alsa_device_secondary)
        except Exception:
            LOGGER.warning("Secondary mic unavailable — direction detection disabled")
            self._sec_proc = None

    def _secondary_loop(self) -> None:
        while not self._stop_event.is_set() and self._sec_proc:
            chunk = self._sec_proc.stdout.read(CHUNK_BYTES)
            if not chunk or len(chunk) < CHUNK_BYTES:
                break
            rms = self._rms(chunk)
            with self._sec_lock:
                self._sec_rms = rms

    def _estimate_direction(self, primary_rms: float) -> None:
        """Estimate direction from RMS difference between two mics.

        Positive = sound is closer to primary (right-ish).
        Negative = sound is closer to secondary (left-ish).
        """
        with self._sec_lock:
            sec_rms = self._sec_rms

        if primary_rms < 1 and sec_rms < 1:
            return

        total = primary_rms + sec_rms
        if total < 100:
            return

        # Normalise to -1..1: positive means primary mic is louder
        direction = (primary_rms - sec_rms) / total
        direction = max(-1.0, min(1.0, direction))
        LOGGER.debug("Sound direction: %.2f (pri=%.0f sec=%.0f)", direction, primary_rms, sec_rms)

        with self._listeners_lock:
            consumers = list(self._direction_consumers)
        for consumer in consumers:
            try:
                consumer(direction)
            except Exception:
                LOGGER.exception("Direction consumer error")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _rms(raw: bytes) -> float:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(samples ** 2)))

    def _dispatch(self, text: str) -> None:
        with self._listeners_lock:
            consumers = list(self._transcript_consumers)
        for consumer in consumers:
            try:
                consumer(text)
            except Exception:
                LOGGER.exception("Transcript consumer raised an exception")
