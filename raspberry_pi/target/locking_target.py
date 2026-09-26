#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Target Locking & Person Tracking Subsystem
========================================================================
File: raspberry_pi/target/locking_target.py
Adheres to:
- docs/2_system_design/state_machine.md
- docs/3_software_design/software_architecture.md
- docs/3_software_design/module_specification.md

Responsibility:
    1. Person Tracking (PersonTracker):
       - Associative tracking across frames using IoU (Intersection-over-Union)
         cost matching to maintain stable, persistent track IDs.
       - Handles brief occlusions and detection dropouts.

    2. Spatial Gesture Association:
       - Maps MediaPipe hand coordinates to the specific person performing the gesture
         (verifying the hand is within the person's bounding box and arm reach zone).

    3. Target Locking & Authorization (TargetLockManager):
       - Locks onto the specific individual who authenticated NEXUS with the password gesture.
       - Anti-Hijack: While locked, password gestures from other individuals are rejected.
       - Automatic Loss Timeout: If the locked target is continuously missing/lost for
         longer than `loss_timeout_seconds` (default: 3.0s), triggers TARGET_LOST_TIMEOUT
         to command NEXUS ON -> NEXUS OFF.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict
import time
import numpy as np
import cv2

# Import detection interfaces
from raspberry_pi.vision.person_detection import PersonDetection
from raspberry_pi.vision.gesture_recognition import GestureDetection


# =============================================================================
# 1. Enums & Data Structures
# =============================================================================
class TargetStatus(Enum):
    """Status of the target lock."""
    UNLOCKED = "Unlocked"
    LOCKED = "Locked"
    LOST = "Lost"


class TargetEvent(Enum):
    """Events emitted by TargetLockManager during pipeline updates."""
    NONE = "none"
    TARGET_LOCKED = "target_locked"
    TARGET_REACQUIRED = "target_reacquired"
    TARGET_LOST = "target_lost"
    TARGET_LOST_TIMEOUT = "target_lost_timeout"
    TARGET_UNLOCKED = "target_unlocked"


@dataclass
class TrackedPerson:
    """
    Persistent track representation of an individual across video frames.

    Attributes:
        track_id: Unique integer ID assigned to this track.
        bbox: Bounding box tuple (x1, y1, x2, y2) in pixel coordinates.
        confidence: Detection confidence score from YOLO.
        class_id: Detector class ID (0 for person).
        missed_frames: Number of consecutive frames this track was not detected.
        hit_streak: Number of consecutive frames this track was matched.
        age: Total number of frames since this track was first created.
        last_seen_timestamp: Epoch timestamp when this track was last updated.
    """
    track_id: int
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int = 0
    missed_frames: int = 0
    hit_streak: int = 1
    age: int = 1
    last_seen_timestamp: float = field(default_factory=time.time)

    @property
    def x1(self) -> int:
        return self.bbox[0]

    @property
    def y1(self) -> int:
        return self.bbox[1]

    @property
    def x2(self) -> int:
        return self.bbox[2]

    @property
    def y2(self) -> int:
        return self.bbox[3]

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> Tuple[float, float]:
        """Centroid (xc, yc) in pixel coordinates."""
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    def get_dx_normalized(self, frame_width: int) -> float:
        """
        Calculates normalized horizontal offset from camera center.
        Returns:
            float in [-1.0, 1.0]:
                - 0.0: Target is centered in the camera frame.
                - Negative (-1.0 to 0.0): Target is to the LEFT of center.
                - Positive (0.0 to +1.0): Target is to the RIGHT of center.
        """
        if frame_width <= 0:
            return 0.0
        center_x = self.center[0]
        frame_center = frame_width / 2.0
        return float((center_x - frame_center) / frame_center)

    def contains_point(
        self,
        px: float,
        py: float,
        reach_x_margin: float = 0.40,
        reach_y_margin: float = 0.20
    ) -> bool:
        """
        Tests if a point (e.g. hand centroid) is inside this person's bounding box
        or within their natural arm-reach zone.

        Args:
            px, py: Query coordinates (pixel units).
            reach_x_margin: Extra horizontal reach allowance as ratio of box width.
            reach_y_margin: Extra vertical reach allowance as ratio of box height.
        """
        margin_x = self.width * reach_x_margin
        margin_y = self.height * reach_y_margin

        min_x = self.x1 - margin_x
        max_x = self.x2 + margin_x
        min_y = self.y1 - margin_y
        max_y = self.y2 + margin_y

        return (min_x <= px <= max_x) and (min_y <= py <= max_y)


# =============================================================================
# 2. IoU Calculation Helper
# =============================================================================
def calculate_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    """Computes standard Intersection-over-Union (IoU) between two bounding boxes."""
    xa = max(box_a[0], box_b[0])
    ya = max(box_a[1], box_b[1])
    xb = min(box_a[2], box_b[2])
    yb = min(box_a[3], box_b[3])

    inter_w = max(0, xb - xa)
    inter_h = max(0, yb - ya)
    inter_area = inter_w * inter_h

    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union_area = float(area_a + area_b - inter_area)

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


# =============================================================================
# 3. Person Tracker (IoU-based Multi-Object Tracking)
# =============================================================================
class PersonTracker:
    """
    Lightweight, fast multi-person tracker using IoU assignment.
    Maintains persistent IDs for persons across successive frames.
    """

    def __init__(
        self,
        max_missed_frames: int = 150,
        iou_threshold: float = 0.25
    ):
        """
        Args:
            max_missed_frames: Maximum frames a track can be missed before termination.
            iou_threshold: Minimum IoU to associate a detection with an existing track.
        """
        self.max_missed_frames = max_missed_frames
        self.iou_threshold = iou_threshold
        self.next_track_id: int = 1
        self.tracks: Dict[int, TrackedPerson] = {}

    def reset(self):
        """Clears all tracks and resets ID counter."""
        self.tracks.clear()
        self.next_track_id = 1

    def update(self, detections: List[PersonDetection]) -> List[TrackedPerson]:
        """
        Updates tracks with new detections from the current frame.

        Args:
            detections: List of PersonDetection objects from person_detector.

        Returns:
            List of active TrackedPerson objects for the current frame.
        """
        now = time.time()
        track_ids = list(self.tracks.keys())
        num_tracks = len(track_ids)
        num_dets = len(detections)

        # Increment age for all active tracks
        for track in self.tracks.values():
            track.age += 1

        matched_tracks = set()
        matched_dets = set()

        if num_tracks > 0 and num_dets > 0:
            # Build IoU similarity matrix
            iou_matrix = np.zeros((num_tracks, num_dets), dtype=np.float32)
            for i, tid in enumerate(track_ids):
                for j, det in enumerate(detections):
                    iou_matrix[i, j] = calculate_iou(self.tracks[tid].bbox, det.bbox)

            # Greedy matching sorted by highest IoU
            matched_indices = []
            while True:
                if iou_matrix.size == 0 or np.max(iou_matrix) < self.iou_threshold:
                    break
                max_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                i, j = int(max_idx[0]), int(max_idx[1])
                matched_indices.append((track_ids[i], j))
                matched_tracks.add(track_ids[i])
                matched_dets.add(j)
                iou_matrix[i, :] = -1.0
                iou_matrix[:, j] = -1.0

            # Update matched tracks
            for tid, det_idx in matched_indices:
                det = detections[det_idx]
                track = self.tracks[tid]
                track.bbox = det.bbox
                track.confidence = det.confidence
                track.missed_frames = 0
                track.hit_streak += 1
                track.last_seen_timestamp = now

        # Update missed tracks
        for tid in track_ids:
            if tid not in matched_tracks:
                self.tracks[tid].missed_frames += 1
                self.tracks[tid].hit_streak = 0

        # Remove stale tracks that exceeded max_missed_frames
        dead_tracks = [
            tid for tid, track in self.tracks.items()
            if track.missed_frames > self.max_missed_frames
        ]
        for tid in dead_tracks:
            del self.tracks[tid]

        # Initialize new tracks for unmatched detections
        for j, det in enumerate(detections):
            if j not in matched_dets:
                new_track = TrackedPerson(
                    track_id=self.next_track_id,
                    bbox=det.bbox,
                    confidence=det.confidence,
                    class_id=det.class_id,
                    missed_frames=0,
                    hit_streak=1,
                    age=1,
                    last_seen_timestamp=now
                )
                self.tracks[self.next_track_id] = new_track
                self.next_track_id += 1

        # Return all currently visible tracks (missed_frames == 0)
        active_tracks = [t for t in self.tracks.values() if t.missed_frames == 0]
        return active_tracks


# =============================================================================
# 4. Target Lock Manager
# =============================================================================
class TargetLockManager:
    """
    Manages exclusive target locking, spatial gesture association,
    and automatic timeout deactivation when the target is lost.
    """

    def __init__(
        self,
        loss_timeout_seconds: float = 4.0,
        hand_reach_x_margin: float = 0.40,
        hand_reach_y_margin: float = 0.20
    ):
        """
        Args:
            loss_timeout_seconds: Seconds of continuous target loss before deactivation.
            hand_reach_x_margin: Horizontal arm reach margin around person bounding box.
            hand_reach_y_margin: Vertical arm reach margin around person bounding box.
        """
        self.loss_timeout_seconds = loss_timeout_seconds
        self.hand_reach_x_margin = hand_reach_x_margin
        self.hand_reach_y_margin = hand_reach_y_margin

        self.locked_target_id: Optional[int] = None
        self.locked_person: Optional[TrackedPerson] = None
        self.status: TargetStatus = TargetStatus.UNLOCKED

        # Loss timing trackers
        self.loss_start_time: Optional[float] = None
        self.last_seen_time: float = 0.0

    @property
    def is_locked(self) -> bool:
        """True if a target has been designated and not timed out."""
        return self.locked_target_id is not None

    @property
    def is_target_present(self) -> bool:
        """True if target is currently detected and visible in frame."""
        return self.status == TargetStatus.LOCKED

    @property
    def time_lost(self) -> float:
        """Elapsed seconds since target was last seen (0.0 if present)."""
        if self.loss_start_time is None or not self.is_locked:
            return 0.0
        return max(0.0, time.time() - self.loss_start_time)

    @property
    def time_until_timeout(self) -> float:
        """Remaining grace period seconds before target is declared lost (0.0 if not lost)."""
        if self.loss_start_time is None or not self.is_locked:
            return self.loss_timeout_seconds
        remaining = self.loss_timeout_seconds - self.time_lost
        return max(0.0, remaining)

    def associate_gesture_with_person(
        self,
        tracks: List[TrackedPerson],
        gesture: GestureDetection
    ) -> Optional[TrackedPerson]:
        """
        Associates a detected hand gesture with the corresponding person in the camera view.

        Args:
            tracks: List of currently tracked persons in the frame.
            gesture: Detected GestureDetection containing hand center coordinates.

        Returns:
            The TrackedPerson who made the gesture, or None if outside any person's bounds.
        """
        if not tracks:
            return None

        hx, hy = gesture.hand_center

        candidates: List[Tuple[float, TrackedPerson]] = []

        for person in tracks:
            if person.contains_point(
                hx, hy,
                reach_x_margin=self.hand_reach_x_margin,
                reach_y_margin=self.hand_reach_y_margin
            ):
                # Calculate distance between hand center and person center
                px, py = person.center
                dist = np.hypot(hx - px, hy - py)
                candidates.append((dist, person))

        if not candidates:
            return None

        # Pick the candidate closest to the hand center
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def lock_target(self, track_id: int, person: Optional[TrackedPerson] = None) -> None:
        """
        Locks onto a specific person track ID.

        Args:
            track_id: Track ID of the person to follow.
            person: Optional reference to the TrackedPerson object.
        """
        self.locked_target_id = track_id
        self.locked_person = person
        self.status = TargetStatus.LOCKED
        self.last_seen_time = time.time()
        self.loss_start_time = None
        print(f"[TargetLockManager] 🎯 TARGET LOCKED -> Person ID: {track_id}")

    def unlock_target(self) -> None:
        """Releases the target lock."""
        prev_id = self.locked_target_id
        self.locked_target_id = None
        self.locked_person = None
        self.status = TargetStatus.UNLOCKED
        self.loss_start_time = None
        print(f"[TargetLockManager] 🔓 TARGET UNLOCKED (Previous ID: {prev_id})")

    def update(self, tracks: List[TrackedPerson]) -> Tuple[Optional[TrackedPerson], TargetEvent]:
        """
        Updates target status against the current frame's tracked persons.

        Checks:
        1. If no target locked -> returns (None, TargetEvent.NONE)
        2. If locked target is in frame -> updates track, resets loss timer, emits REACQUIRED if was LOST.
        3. If locked target is missing -> starts/increments loss timer.
           - If loss duration >= loss_timeout_seconds (3.0s) -> automatically calls unlock_target()
             and emits TARGET_LOST_TIMEOUT.

        Returns:
            Tuple of (locked_person_or_last_known, TargetEvent)
        """
        if self.locked_target_id is None:
            self.status = TargetStatus.UNLOCKED
            return None, TargetEvent.NONE

        now = time.time()
        matched_person: Optional[TrackedPerson] = None

        # 1. Direct ID match
        for track in tracks:
            if track.track_id == self.locked_target_id:
                matched_person = track
                break

        # 2. Seamless Track ID Transition (when status == LOCKED but track ID changed):
        # If person is still in frame and tracker assigned a new ID, maintain lock without entering LOST!
        if matched_person is None and self.status == TargetStatus.LOCKED and tracks:
            if len(tracks) == 1:
                matched_person = tracks[0]
                prev_id = self.locked_target_id
                self.locked_target_id = matched_person.track_id
                print(f"\n[TargetLockManager] 🔄 TARGET ID RE-ASSOCIATED (Single Person) -> New ID: #{matched_person.track_id} (Previous: #{prev_id})")
            elif self.locked_person is not None:
                # Find track with highest IoU / closest distance
                last_bbox = self.locked_person.bbox
                best_track = None
                best_iou = 0.0
                for track in tracks:
                    iou = calculate_iou(last_bbox, track.bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_track = track
                if best_track is not None and best_iou >= 0.15:
                    matched_person = best_track
                    prev_id = self.locked_target_id
                    self.locked_target_id = matched_person.track_id
                    print(f"\n[TargetLockManager] 🔄 TARGET ID RE-ASSOCIATED (IoU {best_iou:.2f}) -> New ID: #{matched_person.track_id} (Previous: #{prev_id})")

        # 3. Spatial Re-acquisition during LOST state:
        # If target was temporarily lost (<5.0s) and detections reappear,
        # re-acquire the target even if tracker assigned a new track ID!
        if matched_person is None and self.status == TargetStatus.LOST and tracks:
            if len(tracks) == 1:
                # Exactly 1 person in front of the robot -> re-acquire as target
                matched_person = tracks[0]
                prev_id = self.locked_target_id
                self.locked_target_id = matched_person.track_id
                print(f"\n[TargetLockManager] 🔄 TARGET REACQUIRED (Single Person) -> New ID: #{matched_person.track_id} (Previous: #{prev_id})")
            elif self.locked_person is not None:
                # Multiple persons -> match closest to last known bounding box/position
                last_bbox = self.locked_person.bbox
                last_cx = (last_bbox[0] + last_bbox[2]) / 2.0
                last_cy = (last_bbox[1] + last_bbox[3]) / 2.0
                best_track = None
                best_score = -float("inf")
                for track in tracks:
                    iou = calculate_iou(last_bbox, track.bbox)
                    tcx = (track.bbox[0] + track.bbox[2]) / 2.0
                    tcy = (track.bbox[1] + track.bbox[3]) / 2.0
                    dist = np.hypot(tcx - last_cx, tcy - last_cy)
                    score = (iou * 1000.0) - dist
                    if score > best_score:
                        best_score = score
                        best_track = track
                if best_track is not None:
                    matched_person = best_track
                    prev_id = self.locked_target_id
                    self.locked_target_id = matched_person.track_id
                    print(f"\n[TargetLockManager] 🔄 TARGET REACQUIRED (Spatial Proximity) -> New ID: #{matched_person.track_id} (Previous: #{prev_id})")
            else:
                # Multiple persons and locked_person was None -> pick largest/closest track
                tracks_sorted = sorted(tracks, key=lambda t: (t.bbox[2]-t.bbox[0])*(t.bbox[3]-t.bbox[1]), reverse=True)
                matched_person = tracks_sorted[0]
                prev_id = self.locked_target_id
                self.locked_target_id = matched_person.track_id
                print(f"\n[TargetLockManager] 🔄 TARGET REACQUIRED (Prominent Person) -> New ID: #{matched_person.track_id} (Previous: #{prev_id})")

        if matched_person is not None:
            # Target is visible!
            was_lost = (self.status == TargetStatus.LOST)
            self.locked_person = matched_person
            self.status = TargetStatus.LOCKED
            self.last_seen_time = now
            self.loss_start_time = None

            event = TargetEvent.TARGET_REACQUIRED if was_lost else TargetEvent.NONE
            return self.locked_person, event

        # Target is NOT visible in current frame
        if self.loss_start_time is None:
            # First frame target was lost
            self.loss_start_time = now
            self.status = TargetStatus.LOST
            print(f"[TargetLockManager] ⚠️ TARGET LOST -> Track ID: {self.locked_target_id}. Timeout in {self.loss_timeout_seconds:.1f}s...")
            return self.locked_person, TargetEvent.TARGET_LOST

        # Target continues to be lost
        elapsed_lost = now - self.loss_start_time
        if elapsed_lost >= self.loss_timeout_seconds:
            # Target has been missing beyond grace period!
            timed_out_id = self.locked_target_id
            print(f"\n[TargetLockManager] 🚨 TARGET LOSS TIMEOUT ({elapsed_lost:.2f}s >= {self.loss_timeout_seconds}s)!")
            print(f"                   Auto-deactivating target ID: {timed_out_id} -> NEXUS OFF.")
            self.unlock_target()
            return None, TargetEvent.TARGET_LOST_TIMEOUT

        self.status = TargetStatus.LOST
        return self.locked_person, TargetEvent.NONE


# =============================================================================
# 4.5 Fast Visual Object Tracker (OpenCV KCF/CSRT/MIL)
# =============================================================================
class FastVisualTracker:
    """
    OpenCV High-Speed Visual Object Tracker.
    Tracks a locked target frame-by-frame with ~2-4 ms compute time on Raspberry Pi 4,
    eliminating the heavy 450-700ms YOLO inference on every frame during NEXUS ON.
    """
    def __init__(self):
        self.tracker = None
        self.is_tracking = False
        self.current_bbox: Optional[Tuple[int, int, int, int]] = None

    def _create_tracker(self):
        # Prefer KCF (~2 ms on Raspberry Pi) or MIL/CSRT
        for creator in [
            lambda: cv2.TrackerKCF_create() if hasattr(cv2, "TrackerKCF_create") else None,
            lambda: cv2.TrackerKCF.create() if hasattr(cv2, "TrackerKCF") and hasattr(cv2.TrackerKCF, "create") else None,
            lambda: cv2.TrackerMIL_create() if hasattr(cv2, "TrackerMIL_create") else None,
            lambda: cv2.TrackerMIL.create() if hasattr(cv2, "TrackerMIL") and hasattr(cv2.TrackerMIL, "create") else None,
            lambda: cv2.TrackerCSRT_create() if hasattr(cv2, "TrackerCSRT_create") else None,
            lambda: cv2.TrackerCSRT.create() if hasattr(cv2, "TrackerCSRT") and hasattr(cv2.TrackerCSRT, "create") else None,
        ]:
            try:
                t = creator()
                if t is not None:
                    return t
            except Exception:
                continue
        return None

    def start_track(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
        """Initializes tracker on target bounding box (x1, y1, x2, y2)."""
        if frame is None or frame.size == 0 or bbox is None:
            return False

        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        # Clamp strictly within image boundaries to prevent OpenCV ROI crashes
        x1 = max(0, min(fw - 15, x1))
        y1 = max(0, min(fh - 15, y1))
        x2 = max(x1 + 10, min(fw, x2))
        y2 = max(y1 + 10, min(fh, y2))
        w = x2 - x1
        h = y2 - y1
        rect = (x1, y1, w, h)

        try:
            self.tracker = self._create_tracker()
            if self.tracker is not None:
                self.tracker.init(frame, rect)
                self.is_tracking = True
                self.current_bbox = (x1, y1, x2, y2)
                return True
        except Exception as e:
            print(f"[FastVisualTracker] Warning starting tracker: {e}")

        self.is_tracking = False
        return False

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[Tuple[int, int, int, int]]]:
        """
        Updates target position on new frame.
        Execution time: ~2-4 ms on Raspberry Pi CPU!
        """
        if not self.is_tracking or self.tracker is None or frame is None:
            return False, None

        fh, fw = frame.shape[:2]
        try:
            ok, rect = self.tracker.update(frame)
            if ok:
                x, y, w, h = [int(v) for v in rect]
                x1 = max(0, min(fw - 1, x))
                y1 = max(0, min(fh - 1, y))
                x2 = max(0, min(fw, x + w))
                y2 = max(0, min(fh, y + h))

                if (x2 - x1) > 15 and (y2 - y1) > 20:
                    self.current_bbox = (x1, y1, x2, y2)
                    return True, self.current_bbox
        except Exception:
            pass

        self.is_tracking = False
        return False, None

    def stop(self):
        """Stops the visual tracker."""
        self.is_tracking = False
        self.tracker = None
        self.current_bbox = None


# =============================================================================
# 5. Target & Tracking Overlay Drawing Helper
# =============================================================================
def draw_target_overlay(
    canvas: np.ndarray,
    tracks: List[TrackedPerson],
    target_manager: TargetLockManager,
    frame_width: int
) -> np.ndarray:
    """
    Renders person tracking boxes and high-contrast locked target indicators.

    Visual encoding:
    - Normal tracked persons: Green bounding box with ID and confidence.
    - Locked target (LOCKED): Bold Gold/Amber box with target reticle crosshair,
      corner brackets, and steering offset dx display.
    - Locked target (LOST): Orange warning indicator showing grace period countdown.
    """
    locked_id = target_manager.locked_target_id
    is_target_lost = (target_manager.status == TargetStatus.LOST)
    time_left = target_manager.time_until_timeout

    for track in tracks:
        x1, y1, x2, y2 = track.bbox
        is_locked_target = (locked_id is not None and track.track_id == locked_id)

        if is_locked_target:
            # Target box in Gold / Amber
            target_color = (0, 215, 255)  # BGR: Gold
            cv2.rectangle(canvas, (x1, y1), (x2, y2), target_color, 3)

            # Draw target corner brackets for futuristic HUD look
            corner_len = min(20, track.width // 4, track.height // 4)
            # Top-left
            cv2.line(canvas, (x1, y1), (x1 + corner_len, y1), (0, 255, 255), 4)
            cv2.line(canvas, (x1, y1), (x1, y1 + corner_len), (0, 255, 255), 4)
            # Top-right
            cv2.line(canvas, (x2, y1), (x2 - corner_len, y1), (0, 255, 255), 4)
            cv2.line(canvas, (x2, y1), (x2, y1 + corner_len), (0, 255, 255), 4)
            # Bottom-left
            cv2.line(canvas, (x1, y2), (x1 + corner_len, y2), (0, 255, 255), 4)
            cv2.line(canvas, (x1, y2), (x1, y2 - corner_len), (0, 255, 255), 4)
            # Bottom-right
            cv2.line(canvas, (x2, y2), (x2 - corner_len, y2), (0, 255, 255), 4)
            cv2.line(canvas, (x2, y2), (x2 - corner_len, y2), (0, 255, 255), 4)

            # Center crosshair reticle
            cx, cy = int(track.center[0]), int(track.center[1])
            cv2.circle(canvas, (cx, cy), 14, (0, 215, 255), 2)
            cv2.drawMarker(canvas, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 24, 2)

            # Steering offset dx
            dx = track.get_dx_normalized(frame_width)
            tag = f"TARGET [ID: {track.track_id}] | dx: {dx:+.2f}"
            (tw, th), bl = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            ty1 = max(0, y1 - th - bl - 6)
            cv2.rectangle(canvas, (x1, ty1), (x1 + tw + 8, y1), target_color, -1)
            cv2.putText(canvas, tag, (x1 + 4, y1 - bl - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2, cv2.LINE_AA)

        else:
            # Standard tracked person in Green
            person_color = (0, 255, 0)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), person_color, 2)
            cx, cy = int(track.center[0]), int(track.center[1])
            cv2.drawMarker(canvas, (cx, cy), (0, 180, 0), cv2.MARKER_CROSS, 10, 1)

            tag = f"ID: {track.track_id} ({track.confidence:.0%})"
            (tw, th), bl = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            ty1 = max(0, y1 - th - bl - 4)
            cv2.rectangle(canvas, (x1, ty1), (x1 + tw + 6, y1), person_color, -1)
            cv2.putText(canvas, tag, (x1 + 3, y1 - bl - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # If target is currently lost, draw warning banner across canvas
    if target_manager.is_locked and is_target_lost:
        h, w = canvas.shape[:2]
        warn_h = 32
        warn_y = 70
        cv2.rectangle(canvas, (w // 4, warn_y), (3 * w // 4, warn_y + warn_h), (0, 69, 255), -1)
        cv2.rectangle(canvas, (w // 4, warn_y), (3 * w // 4, warn_y + warn_h), (0, 140, 255), 2)
        warn_text = f"TARGET LOST! Reacquiring: {time_left:3.1f}s until NEXUS OFF"
        (wtw, wth), _ = cv2.getTextSize(warn_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        tx = (w - wtw) // 2
        cv2.putText(canvas, warn_text, (tx, warn_y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

    return canvas


# =============================================================================
# 6. Standalone CLI Demo Runner
# =============================================================================
def main():
    import argparse
    from raspberry_pi.vision.person_detection import PersonDetector
    from raspberry_pi.vision.gesture_recognition import GestureRecognizer

    parser = argparse.ArgumentParser(description="NEXUS Target Locking & Tracking Demo")
    parser.add_argument("--source", "-s", type=str, default="0", help="Webcam index or video path")
    parser.add_argument("--loss-timeout", type=float, default=3.0, help="Seconds before target loss timeout")
    args = parser.parse_args()

    src_id = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(src_id)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video source {args.source}")
        return

    detector = PersonDetector()
    tracker = PersonTracker()
    gesture_rec = GestureRecognizer()
    manager = TargetLockManager(loss_timeout_seconds=args.loss_timeout)

    print("\n[Target Demo] Running. Show Victory Sign ✌️ to lock/unlock target.")
    print("              Press 'q' to quit, 'u' to unlock target manually.\n")

    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            frame = cv2.flip(frame, 1)
            persons = detector.detect(frame)
            tracks = tracker.update(persons)
            gestures = gesture_rec.detect(frame, persons=persons)

            locked_person, event = manager.update(tracks)
            if event == TargetEvent.TARGET_LOST_TIMEOUT:
                print("\n[Target Demo] 🚨 Target Lost Timeout reached! Lock cleared.")

            if gesture_rec.check_password_event(gestures):
                pwd_g = next((g for g in gestures if (getattr(g, "is_victory", False) or g.is_open_palm)), None)
                if pwd_g:
                    cand = manager.associate_gesture_with_person(tracks, pwd_g)
                    if not manager.is_locked:
                        if cand:
                            manager.lock_target(cand.track_id, cand)
                    else:
                        if cand and cand.track_id == manager.locked_target_id:
                            manager.unlock_target()

            canvas = draw_target_overlay(frame, tracks, manager, frame.shape[1])
            cv2.imshow("NEXUS Target Locking Demo", canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in [ord('q'), 27]:
                break
            elif key in [ord('u'), ord('U')]:
                manager.unlock_target()
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

