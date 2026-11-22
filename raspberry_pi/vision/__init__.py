"""
NEXUS Vision Package
====================
Contains perception modules:
- person_detection.py: YOLO-based human detector
- gesture_recognition.py: Hand gesture recognition & password authentication
- threaded_camera.py: High-speed asynchronous zero-latency camera reader
"""

try:
    from .person_detection import PersonDetection, PersonDetector
    from .remote_person_detector import RemotePersonDetector
    from .gesture_recognition import GestureDetection, GestureRecognizer
    from .threaded_camera import ThreadedCamera
except ImportError:
    pass

__all__ = [
    "PersonDetection",
    "PersonDetector",
    "RemotePersonDetector",
    "GestureDetection",
    "GestureRecognizer",
    "ThreadedCamera",
]
