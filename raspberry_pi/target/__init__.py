"""
NEXUS Person Follower Robot — Target Tracking & Locking Package
"""

from .locking_target import (
    FastVisualTracker,
    TargetStatus,
    TargetEvent,
    TrackedPerson,
    calculate_iou,
    PersonTracker,
    TargetLockManager,
    draw_target_overlay,
)

__all__ = [
    "FastVisualTracker",
    "TargetStatus",
    "TargetEvent",
    "TrackedPerson",
    "calculate_iou",
    "PersonTracker",
    "TargetLockManager",
    "draw_target_overlay",
]

