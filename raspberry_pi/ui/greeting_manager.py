#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Greeting Manager (3-Layer Anti-Spam)
==================================================================
File: raspberry_pi/ui/greeting_manager.py
Adheres to:
- docs/display_and_greets/greet.md
- docs/2_system_design/state_machine.md (Section 4 & 23)
- docs/2_system_design/subsystem_design.md (Section 10)
- docs/5_validation/acceptance_criteria.md (AC-004)

Responsibility:
    Determines when to trigger the visitor startup greeting without relying
    on inaccurate 2D metric distance calculations. Implements a robust
    3-layer anti-spam mechanism:
    1. Layer 1 (Track-ID Latch): Each tracked person is greeted at most once.
       As long as the same person stands in front of the robot, no repeated audio.
    2. Layer 2 (Scene Empty Reset): If the camera scene is empty (0 persons)
       for at least `empty_reset_seconds` (default 5.0s), the greeted ID memory
       is cleared (re-arming the greeting for new visitors).
    3. Layer 3 (Global Cooldown): A safety cooldown of `cooldown_seconds` (default 15.0s)
       enforces minimum spacing between greetings to prevent audio overlapping in crowds.
"""

import time
from typing import List, Optional, Set, Tuple


class GreetingManager:
    """
    Manages visitor greeting evaluation with a 3-layer anti-spam filter.
    """

    def __init__(
        self,
        cooldown_seconds: float = 15.0,
        empty_reset_seconds: float = 5.0
    ):
        """
        Initialize the Greeting Manager.

        Args:
            cooldown_seconds: Minimum time (seconds) between greetings (Layer 3).
            empty_reset_seconds: Duration (seconds) of scene emptiness required
                                 to reset the greeted track IDs (Layer 2).
        """
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self.empty_reset_seconds = max(1.0, float(empty_reset_seconds))

        # Layer 1: Memory of person track IDs already greeted
        self.greeted_track_ids: Set[int] = set()

        # Layer 2: Scene emptiness tracking
        self.empty_start_time: Optional[float] = None

        # Layer 3: Timestamp of the last greeting
        self.last_greet_time: float = 0.0

        # State tracking
        self.total_greetings_played: int = 0
        self.is_greeting_active: bool = False

    @property
    def time_since_last_greet(self) -> float:
        """Seconds elapsed since the last greeting (inf if never)."""
        if self.last_greet_time == 0.0:
            return float("inf")
        return max(0.0, time.time() - self.last_greet_time)

    @property
    def cooldown_remaining(self) -> float:
        """Remaining cooldown in seconds (0.0 when ready)."""
        rem = self.cooldown_seconds - self.time_since_last_greet
        return max(0.0, rem)

    @property
    def is_in_cooldown(self) -> bool:
        """True if the global greeting cooldown is currently active."""
        return self.cooldown_remaining > 0.0

    def evaluate(
        self,
        tracks: List,
        is_off_state: bool = True
    ) -> Tuple[bool, Optional[int]]:
        """
        Evaluates whether a greeting should be triggered for the current frame.

        Args:
            tracks: List of currently tracked persons (e.g. List[TrackedPerson]).
            is_off_state: True if robot is in OFF / STANDBY state. Greetings only
                          trigger when robot is not actively following.

        Returns:
            Tuple of (should_greet: bool, candidate_track_id: Optional[int])
        """
        now = time.time()

        # 1. Update Layer 2: Scene Empty Detection
        if not tracks:
            if self.empty_start_time is None:
                self.empty_start_time = now
            else:
                elapsed_empty = now - self.empty_start_time
                if elapsed_empty >= self.empty_reset_seconds and self.greeted_track_ids:
                    # Scene has been empty for >= 5 seconds -> Reset memory for new visitors!
                    print(f"[GreetingManager] Scene empty for {elapsed_empty:.1f}s -> Resetting greeted IDs.")
                    self.greeted_track_ids.clear()
            return False, None

        # Scene is NOT empty (there are persons present)
        self.empty_start_time = None

        # 2. Greeting is only permitted while robot is OFF / Standby
        if not is_off_state:
            return False, None

        # 3. Check Layer 3: Global Cooldown Guard
        if self.is_in_cooldown:
            return False, None

        # 4. Check Layer 1: Track-ID Latching
        # Pick the most prominent / first candidate person
        candidate = tracks[0]
        cand_id = getattr(candidate, "track_id", None)
        if cand_id is None:
            return False, None

        if cand_id in self.greeted_track_ids:
            # This person was already greeted in the current session!
            return False, None

        # All 3 layers satisfied! Trigger greeting
        return True, cand_id

    def mark_greeted(self, track_id: int) -> None:
        """
        Marks a person track ID as greeted, records the timestamp,
        and starts the global cooldown.
        """
        self.greeted_track_ids.add(track_id)
        self.last_greet_time = time.time()
        self.total_greetings_played += 1
        self.is_greeting_active = True
        print(f"[GreetingManager] 📢 GREETING TRIGGERED for Person #{track_id} "
              f"(Total Greetings: {self.total_greetings_played})")

    def finish_greeting(self) -> None:
        """Called when the greeting audio playback completes."""
        self.is_greeting_active = False

    def reset(self) -> None:
        """Resets all tracking memory and timers."""
        self.greeted_track_ids.clear()
        self.empty_start_time = None
        self.last_greet_time = 0.0
        self.is_greeting_active = False
