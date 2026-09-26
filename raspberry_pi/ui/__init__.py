"""
NEXUS Person Follower Robot — User Interface & Audio Subsystem
==============================================================
Package: raspberry_pi.ui

Contains modules for human-robot interaction:
- speech_manager.py: Asynchronous voice dialogue player (JARVIS audio character).
- greeting_manager.py: 3-layer anti-spam greeting logic.
- face_display.py: Expressive animated emoji face renderer & fullscreen manager.
"""

from .speech_manager import SpeechManager, VoiceEvent
from .greeting_manager import GreetingManager
from .face_display import FaceDisplayManager, DisplayMode, FaceExpression

__all__ = [
    "SpeechManager",
    "VoiceEvent",
    "GreetingManager",
    "FaceDisplayManager",
    "DisplayMode",
    "FaceExpression",
]
