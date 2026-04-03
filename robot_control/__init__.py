"""Runtime utilities for connecting Axon's sensors to the robotic face."""

from .sensor_data import SensorSample
from .serial_reader import SerialReadWriter, SerialReader
from .emotion_policy import EmotionPolicy
from .face_controller import FaceController
from .gyro_calibrator import GyroCalibrator
from .serial_bridge_config import SerialBridgeConfig
from .serial_bridge_server import SerialBridgeServer

__all__ = [
    "SensorSample",
    "SerialReadWriter",
    "SerialReader",
    "EmotionPolicy",
    "FaceController",
    "GyroCalibrator",
    "SerialBridgeConfig",
    "SerialBridgeServer",
]

try:
    from .speech_listener import SpeechListener
    from .chat_engine import ChatEngine, ChatResponse
    from .speech_synthesizer import SpeechSynthesizer
    from .voice_chat_controller import VoiceChatController, VoiceChatState

    __all__ += [
        "SpeechListener",
        "ChatEngine",
        "ChatResponse",
        "SpeechSynthesizer",
        "VoiceChatController",
        "VoiceChatState",
    ]
except (ImportError, OSError):
    pass
