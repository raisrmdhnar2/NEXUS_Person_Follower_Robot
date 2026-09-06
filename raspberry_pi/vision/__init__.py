"""
NEXUS Vision Package
====================
Contains perception modules:
- person_detection.py: YOLO-based human detector
- gesture_recognition.py: Hand gesture recognition & password authentication
"""

from .person_detection import PersonDetection, PersonDetector
from .gesture_recognition import GestureDetection, GestureRecognizer

__all__ = [
    "PersonDetection",
    "PersonDetector",
    "GestureDetection",
    "GestureRecognizer",
]

