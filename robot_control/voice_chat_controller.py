"""Orchestrates speech recognition, Claude AI, TTS, and face emotions."""

from __future__ import annotations

import logging
import queue
import threading
import time
from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QObject, Signal

from axon_ui import RoboticFaceWidget
from axon_ui.chat_bubble_overlay import ChatBubbleOverlay

from .chat_engine import ChatEngine
from .face_controller import FaceController
from .speech_listener import SpeechListener
from .speech_synthesizer import SpeechSynthesizer

LOGGER = logging.getLogger(__name__)

WAKE_PHRASE = "axon"
# Broad fuzzy matching — just "axon" or anything close
WAKE_VARIANTS = (
    "axon", "action", "axton", "exon", "exxon",
    "alexa", "alex on", "axle", "axel", "accent",
    "akron", "oxygen", "axe on", "acts on", "x on",
    "hey axon", "hey action", "hey alexa", "hey axle",
    "play axon", "play exo", "play exxon",
    "a axon", "the axon", "ok axon", "yo axon",
)
SLEEP_WORDS = ("sleep", "go to sleep", "shut up", "stop talking", "be quiet")
CONVERSATION_TIMEOUT_S = 45.0


class VoiceChatState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class VoiceChatController(QObject):
    """State-machine that coordinates mic -> Claude -> TTS -> face."""

    stateChanged = Signal(object)
    emotionRequested = Signal(str)
    transcriptReady = Signal(str)
    responseReady = Signal(str)
    userBubbleRequested = Signal(str)
    botBubbleRequested = Signal(str)
    speakingChanged = Signal(bool)
    soundDirectionChanged = Signal(float)

    def __init__(
        self,
        face: RoboticFaceWidget,
        face_controller: FaceController,
        listener: SpeechListener,
        chat_engine: ChatEngine,
        synthesizer: SpeechSynthesizer,
        chat_overlay: Optional[ChatBubbleOverlay] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._face = face
        self._face_controller = face_controller
        self._listener = listener
        self._chat_engine = chat_engine
        self._synthesizer = synthesizer
        self._chat_overlay = chat_overlay
        self._state = VoiceChatState.IDLE
        self._stop_event = threading.Event()
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._in_conversation = False
        self._last_interaction: float = 0.0

        self._listener.add_transcript_consumer(self._on_transcript)
        self._listener.add_direction_consumer(self._on_direction)
        self.emotionRequested.connect(self._apply_emotion)
        self.stateChanged.connect(self._on_state_changed)
        self.speakingChanged.connect(self._face.set_speaking)
        self.soundDirectionChanged.connect(self._apply_direction)
        self._face.doubleTapped.connect(self._on_double_tap)
        if self._chat_overlay:
            self.userBubbleRequested.connect(self._chat_overlay.add_user_bubble)
            self.botBubbleRequested.connect(self._chat_overlay.add_bot_bubble)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._listener.start()
        self._thread = threading.Thread(
            target=self._processing_loop,
            name="VoiceChatController",
            daemon=True,
        )
        self._thread.start()
        self._set_state(VoiceChatState.IDLE)
        LOGGER.info("Voice chat started (wake phrase: %r)", WAKE_PHRASE)

    def stop(self) -> None:
        self._stop_event.set()
        self._listener.stop()
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        LOGGER.info("Voice chat stopped")

    # ------------------------------------------------------------------
    # Internal — callbacks (run on listener thread)
    # ------------------------------------------------------------------
    def _on_transcript(self, text: str) -> None:
        self._queue.put(text)

    def _on_direction(self, direction: float) -> None:
        # Only respond to sound direction when NOT speaking (avoid self-feedback)
        if self._state != VoiceChatState.SPEAKING:
            self.soundDirectionChanged.emit(direction)

    # ------------------------------------------------------------------
    # Internal — processing loop (runs on own thread)
    # ------------------------------------------------------------------
    def _processing_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._in_conversation:
                elapsed = time.monotonic() - self._last_interaction
                if elapsed > CONVERSATION_TIMEOUT_S:
                    LOGGER.info("Conversation timed out after %.0fs", elapsed)
                    self._in_conversation = False
                    self._chat_engine.clear_history()
                    self.emotionRequested.emit("neutral")

            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if text is None:
                break

            lower = text.lower().strip()

            # Sleep command — override everything, exit conversation immediately
            if any(s in lower for s in SLEEP_WORDS):
                LOGGER.info("Sleep command detected: %r", lower)
                self._in_conversation = False
                self._chat_engine.clear_history()
                self.emotionRequested.emit("sleepy")
                self.speakingChanged.emit(False)
                self.botBubbleRequested.emit("Zzz...")
                continue

            if not self._in_conversation:
                matched = self._match_wake_word(lower)
                if matched:
                    self._in_conversation = True
                    self._last_interaction = time.monotonic()
                    idx = lower.find(matched)
                    remainder = text[idx + len(matched):].strip()
                    LOGGER.info("Wake word detected (%r), entering conversation", matched)
                    self.botBubbleRequested.emit("Listening...")
                    self.emotionRequested.emit("curious")
                    if remainder:
                        text = remainder
                    else:
                        continue
                else:
                    continue

            self._last_interaction = time.monotonic()
            self._set_state(VoiceChatState.PROCESSING)
            self.transcriptReady.emit(text)
            self.userBubbleRequested.emit(text)
            self.emotionRequested.emit("curious")

            response = self._chat_engine.send(text)

            self._set_state(VoiceChatState.SPEAKING)
            self.emotionRequested.emit(response.emotion)
            self.botBubbleRequested.emit(response.text)
            self.responseReady.emit(response.text)

            self._listener.mute()
            self.speakingChanged.emit(True)
            try:
                self._synthesizer.speak(response.text)
            except Exception:
                LOGGER.exception("TTS failed")
            self.speakingChanged.emit(False)
            self._listener.unmute()

            self._last_interaction = time.monotonic()
            self._set_state(VoiceChatState.IDLE)

    # ------------------------------------------------------------------
    # Internal — Qt slots (run on main thread via signal)
    # ------------------------------------------------------------------
    def _apply_emotion(self, emotion: str) -> None:
        available = tuple(self._face.available_emotions())
        if emotion in available:
            self._face.set_emotion(emotion)

    def _on_state_changed(self, state: VoiceChatState) -> None:
        held = state in (VoiceChatState.PROCESSING, VoiceChatState.SPEAKING)
        self._face_controller.set_emotion_hold(held)

    def _on_double_tap(self) -> None:
        if not self._in_conversation:
            self._in_conversation = True
            self._last_interaction = time.monotonic()
            LOGGER.info("Conversation activated by double tap")
            self.botBubbleRequested.emit("Listening...")
            self.emotionRequested.emit("curious")

    def _apply_direction(self, direction: float) -> None:
        """Nudge the face yaw toward the sound source, unless gyro movement is stronger."""
        current_yaw = self._face._orientation.get("yaw", 0.0)
        # Sound-based target: map -1..1 to -20..20 degrees
        sound_yaw = direction * 20.0
        # Blend gently: only apply if the gyro isn't producing large movement
        gyro_strength = abs(current_yaw)
        if gyro_strength < 10.0:
            # Smooth toward sound direction
            blended = current_yaw * 0.7 + sound_yaw * 0.3
            self._face.set_orientation(yaw=blended)

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _match_wake_word(text: str) -> str | None:
        for variant in WAKE_VARIANTS:
            if variant in text:
                return variant
        return None

    def _set_state(self, state: VoiceChatState) -> None:
        self._state = state
        self.stateChanged.emit(state)
        LOGGER.debug("Voice chat state: %s", state.name)
