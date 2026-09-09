#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Follow Controller (Steering Evaluator)
===================================================================
File: follow_controller.py (also mirrored in raspberry_pi/control/follow_controller.py)
Adheres to:
- docs/revision/revision_concept.md
- docs/3_software_design/software_architecture.md

Responsibility:
    Evaluates the horizontal offset (dx) of the locked person target
    and determines the 1-byte discrete command for the ESP32:
        '-' : Target is to the LEFT (Turn Left)
        '+' : Target is to the RIGHT (Turn Right)
        'x' : Target is within the deadzone (Center / Forward Ready)
        's' : Robot is OFF, target is lost, or standby (STOP)

Deadzone:
    Default ±0.15 (15% from image center). Prevents rapid hunting
    oscillations caused by natural body sway.
"""

from enum import Enum
from typing import Optional, Tuple
import numpy as np

# Import domain entities
from locking_target import TargetLockManager, TrackedPerson, TargetStatus


class SteeringCommand(str, Enum):
    """Discrete 1-byte command symbols sent to ESP32."""
    LEFT = "-"
    RIGHT = "+"
    CENTER = "x"
    STOP = "s"

    @property
    def label(self) -> str:
        """Human-readable display label."""
        labels = {
            SteeringCommand.LEFT: "BELOK KIRI [-]",
            SteeringCommand.RIGHT: "BELOK KANAN [+]",
            SteeringCommand.CENTER: "CENTER [x]",
            SteeringCommand.STOP: "STOP [s]",
        }
        return labels.get(self, self.value)

    @property
    def short_desc(self) -> str:
        descriptions = {
            SteeringCommand.LEFT: "Turn Left",
            SteeringCommand.RIGHT: "Turn Right",
            SteeringCommand.CENTER: "Target Aligned",
            SteeringCommand.STOP: "Motors Off",
        }
        return descriptions.get(self, "")


class FollowController:
    """
    Steering direction evaluator with deadzone hysteresis.
    Translates perception tracking data into discrete steering symbols.
    """

    def __init__(self, deadzone: float = 0.15):
        """
        Args:
            deadzone: Half-width of center zone in normalized [-1.0, 1.0] range.
                      Target with |dx| <= deadzone is considered CENTER ('x').
        """
        self.deadzone = deadzone
        self.last_command = SteeringCommand.STOP
        self.last_dx: float = 0.0

    def evaluate(
        self,
        is_active: bool,
        target_manager: TargetLockManager,
        target_person: Optional[TrackedPerson],
        frame_width: int
    ) -> SteeringCommand:
        """
        Determines the steering command for the current frame.

        Args:
            is_active: True if robot state machine is in NEXUS ON.
            target_manager: Active TargetLockManager instance.
            target_person: TrackedPerson currently locked, or None.
            frame_width: Pixel width of camera frame.

        Returns:
            SteeringCommand enum member (LEFT, RIGHT, CENTER, or STOP).
        """
        # 1. If robot is OFF, standby, or target is missing/unlocked -> STOP
        if not is_active:
            self.last_command = SteeringCommand.STOP
            self.last_dx = 0.0
            return SteeringCommand.STOP

        if not target_manager.is_locked or target_manager.status != TargetStatus.LOCKED:
            self.last_command = SteeringCommand.STOP
            self.last_dx = 0.0
            return SteeringCommand.STOP

        if target_person is None:
            self.last_command = SteeringCommand.STOP
            self.last_dx = 0.0
            return SteeringCommand.STOP

        # 2. Calculate normalized horizontal offset dx in [-1.0, 1.0]
        dx = target_person.get_dx_normalized(frame_width)
        self.last_dx = dx

        # 3. Classify direction based on deadzone
        if dx < -self.deadzone:
            cmd = SteeringCommand.LEFT
        elif dx > self.deadzone:
            cmd = SteeringCommand.RIGHT
        else:
            cmd = SteeringCommand.CENTER

        self.last_command = cmd
        return cmd


def main():
    """Simple unit test demo."""
    print("Testing FollowController logic...")
    ctrl = FollowController(deadzone=0.15)

    # Mock manager
    class MockTargetManager:
        is_locked = True
        status = TargetStatus.LOCKED

    # Mock person
    class MockPerson:
        def __init__(self, cx, w):
            self.cx = cx
            self.w = w
        @property
        def center(self):
            return (self.cx, 240.0)
        def get_dx_normalized(self, fw):
            return (self.cx - fw / 2.0) / (fw / 2.0)

    mgr = MockTargetManager()
    fw = 640

    # 1. Target at center (320px -> dx = 0.0)
    p_center = MockPerson(320, fw)
    cmd = ctrl.evaluate(True, mgr, p_center, fw)
    assert cmd == SteeringCommand.CENTER, f"Expected CENTER, got {cmd}"
    print(f"Center (320px): {cmd.label} ✓")

    # 2. Target at left (200px -> dx = -0.375)
    p_left = MockPerson(200, fw)
    cmd = ctrl.evaluate(True, mgr, p_left, fw)
    assert cmd == SteeringCommand.LEFT, f"Expected LEFT, got {cmd}"
    print(f"Left (200px): {cmd.label} ✓")

    # 3. Target at right (450px -> dx = +0.406)
    p_right = MockPerson(450, fw)
    cmd = ctrl.evaluate(True, mgr, p_right, fw)
    assert cmd == SteeringCommand.RIGHT, f"Expected RIGHT, got {cmd}"
    print(f"Right (450px): {cmd.label} ✓")

    # 4. Inactive state (NEXUS OFF) -> STOP
    cmd = ctrl.evaluate(False, mgr, p_center, fw)
    assert cmd == SteeringCommand.STOP, f"Expected STOP, got {cmd}"
    print(f"NEXUS OFF: {cmd.label} ✓")

    print("\nAll FollowController tests passed successfully!")


if __name__ == "__main__":
    main()

