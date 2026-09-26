"""
NEXUS Person Follower Robot — User Interface & Audio Subsystem
==============================================================
Package: raspberry_pi.ui

Contains modules for human-robot interaction:
- speech_manager.py: Asynchronous voice dialogue player (JARVIS audio character).
- greeting_manager.py: 3-layer anti-spam greeting logic.
"""

from .speech_manager import SpeechManager, VoiceEvent
from .greeting_manager import GreetingManager

__all__ = [
    "SpeechManager",
    "VoiceEvent",
    "GreetingManager",
]
