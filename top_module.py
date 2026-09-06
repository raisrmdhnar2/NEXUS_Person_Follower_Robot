#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Central Top Module (top_module.py)
=================================================================
File: top_module.py (Application Coordinator)
Adheres to:
- docs/2_system_design/state_machine.md
- docs/3_software_design/software_architecture.md (Section 3: Layer Architecture)
- docs/3_software_design/module_specification.md (Section 2: Application Coordinator)

Responsibility:
    Acts as the top-level system coordinator. Orchestrates:
    1. Video Acquisition (webcam / video / camera stream)
    2. Person Detection (YOLO: person_detection.py)
    3. Multi-Person Tracking (IoU Tracker: locking_target.py)
    4. Gesture Recognition (MediaPipe Tasks Open-Palm: gesture_recognition.py)
    5. Target Locking & Authorization (TargetLockManager: locking_target.py)
       - Exclusive target lock on the person presenting the password
       - Anti-hijack (rejection of gestures from unauthorized persons)
       - Automatic transition to NEXUS OFF if target is lost for > 3.0s
    6. State Machine Coordination (NexusStateMachine)
    7. Composite HUD & Telemetry Visualization

Usage:
    python3 top_module.py
    python3 top_module.py --source 0
    python3 top_module.py --source path/to/video.mp4
    python3 top_module.py --no-flip  (disable horizontal un-mirror)
"""

import argparse
import sys
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import NEXUS vision & target tracking modules
from raspberry_pi.vision.person_detection import PersonDetection, PersonDetector
from raspberry_pi.vision.gesture_recognition import GestureDetection, GestureRecognizer
from locking_target import (
    PersonTracker,
    TargetLockManager,
    TrackedPerson,
    TargetStatus,
    TargetEvent,
    draw_target_overlay
)


# =============================================================================
# 1. State Machine Definitions
# =============================================================================
class NexusState(Enum):
    """
    Operating states for NEXUS robot.
    Matches docs/2_system_design/state_machine.md.
    """
    OFF = "Nexus Off"
    ON = "Nexus On"


class NexusStateMachine:
    """
    State machine coordinator for NEXUS.
    Manages transitions between 'Nexus Off' and 'Nexus On'.
    """

    def __init__(self, toggle_cooldown: float = 3.0):
        self.state: NexusState = NexusState.OFF
        self.toggle_cooldown: float = toggle_cooldown
        self.last_transition_time: float = 0.0
        self.transition_count: int = 0
        self.status_message: str = "System Initialized. State: Nexus Off"

    @property
    def cooldown_remaining(self) -> float:
        """Remaining cooldown in seconds (0.0 when ready for next gesture)."""
        rem = self.toggle_cooldown - (time.time() - self.last_transition_time)
        return max(0.0, rem)

    @property
    def is_in_cooldown(self) -> bool:
        return self.cooldown_remaining > 0.0

    def force_off(self, reason: str = "Target Lost Timeout") -> None:
        """
        Forces transition to NEXUS OFF regardless of cooldown
        (used for safety deactivations like target loss timeout).
        """
        self.state = NexusState.OFF
        self.status_message = f"{reason} -> NEXUS OFF"
        self.last_transition_time = time.time()
        self.transition_count += 1
        print(f"\n[STATE TRANSITION #{self.transition_count}] >>> NEXUS OFF <<< ({reason})")

    def handle_password_gesture(self, reason: str = "Password Accepted") -> bool:
        """
        Executes state transition when an authorized password gesture occurs.
        Enforces toggle cooldown to prevent rapid state flickering.
        """
        now = time.time()
        if (now - self.last_transition_time) < self.toggle_cooldown:
            return False

        self.last_transition_time = now
        self.transition_count += 1

        if self.state == NexusState.OFF:
            self.state = NexusState.ON
            self.status_message = f"{reason}! -> NEXUS ON (Cooldown {self.toggle_cooldown:.1f}s)"
            print(f"\n[STATE TRANSITION #{self.transition_count}] >>> NEXUS ON <<< ({reason})")
        else:
            self.state = NexusState.OFF
            self.status_message = f"{reason}! -> NEXUS OFF (Cooldown {self.toggle_cooldown:.1f}s)"
            print(f"\n[STATE TRANSITION #{self.transition_count}] >>> NEXUS OFF <<< ({reason})")

        return True


# =============================================================================
# 2. HUD & Overlay Visualization
# =============================================================================
def draw_top_module_hud(
    frame: np.ndarray,
    state: NexusState,
    tracks: List[TrackedPerson],
    gestures: List[GestureDetection],
    target_manager: TargetLockManager,
    status_msg: str,
    latency_ms: float,
    fps: float,
    is_flipped: bool,
    cooldown_remaining: float = 0.0
) -> np.ndarray:
    """
    Renders top module HUD with Target Locking, Hand Gestures,
    Master State Banner, and system telemetry.
    """
    canvas = frame.copy()
    h, w = canvas.shape[:2]

    # -------------------------------------------------------------------------
    # A. Draw Tracked Persons & Locked Target Overlay
    # -------------------------------------------------------------------------
    canvas = draw_target_overlay(
        canvas=canvas,
        tracks=tracks,
        target_manager=target_manager,
        frame_width=w
    )

    # -------------------------------------------------------------------------
    # B. Draw Hand Gesture Detections (Blue or Gold Box)
    # -------------------------------------------------------------------------
    for g in gestures:
        hx1, hy1, hx2, hy2 = g.hand_bbox
        is_pwd = g.is_open_palm
        box_color = (0, 215, 255) if is_pwd else (255, 140, 0)  # Gold if Password, else Blue

        cv2.rectangle(canvas, (hx1, hy1), (hx2, hy2), box_color, 2)

        label = "🖐️ PASSWORD (Open Palm)" if is_pwd else f"Hand ({g.handedness})"
        (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ty1 = max(0, hy1 - th - bl - 4)
        cv2.rectangle(canvas, (hx1, ty1), (hx1 + tw + 6, hy1), box_color, -1)
        cv2.putText(canvas, label, (hx1 + 3, hy1 - bl - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # -------------------------------------------------------------------------
    # C. Top Center Master State Banner
    # -------------------------------------------------------------------------
    banner_w, banner_h = 380, 54
    bx1 = (w - banner_w) // 2
    by1 = 12
    bx2 = bx1 + banner_w
    by2 = by1 + banner_h

    if state == NexusState.ON:
        if target_manager.status == TargetStatus.LOST:
            # Flashing Amber / Crimson Banner when target is missing
            bg_color = (0, 69, 255)
            border_color = (0, 140, 255)
            time_left = target_manager.time_until_timeout
            state_text = f"⚠️ TARGET LOST ({time_left:3.1f}s)"
            sub_text = "Searching... Auto NEXUS OFF if not found"
        elif target_manager.locked_target_id is not None:
            # Vibrant Green Banner with locked target ID
            bg_color = (0, 160, 0)
            border_color = (0, 255, 100)
            state_text = f"NEXUS ON — TARGET #{target_manager.locked_target_id}"
            if cooldown_remaining > 0.0:
                sub_text = f"Following Active | Cooldown: {cooldown_remaining:3.1f}s..."
            else:
                sub_text = "Following Active | 🖐️ Target Palm to Deactivate"
        else:
            bg_color = (0, 160, 0)
            border_color = (0, 255, 100)
            state_text = "NEXUS ON"
            sub_text = "Active | 🖐️ Open Palm to Deactivate"
    else:
        # Crimson / Dark Red Banner for OFF
        bg_color = (30, 30, 160)
        border_color = (60, 60, 255)
        state_text = "NEXUS OFF"
        if cooldown_remaining > 0.0:
            sub_text = f"Standby | Cooldown: {cooldown_remaining:3.1f}s..."
        else:
            sub_text = "Standby | 🖐️ Open Palm to Lock & Follow"

    cv2.rectangle(canvas, (bx1, by1), (bx2, by2), bg_color, -1)
    cv2.rectangle(canvas, (bx1, by1), (bx2, by2), border_color, 2)

    # Main State Text
    (tw, th), bl = cv2.getTextSize(state_text, cv2.FONT_HERSHEY_SIMPLEX, 0.78, 2)
    tx = bx1 + (banner_w - tw) // 2
    ty = by1 + 28
    cv2.putText(canvas, state_text, (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.78, (255, 255, 255), 2, cv2.LINE_AA)

    # Subtitle Instruction / Cooldown Text
    (stw, sth), sbl = cv2.getTextSize(sub_text, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
    stx = bx1 + (banner_w - stw) // 2
    sty = by1 + 46
    cv2.putText(canvas, sub_text, (stx, sty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (235, 235, 235), 1, cv2.LINE_AA)

    # -------------------------------------------------------------------------
    # D. Telemetry & Counters
    # -------------------------------------------------------------------------
    # Top Left: Perception & Target Status Box
    cv2.rectangle(canvas, (10, 10), (200, 75), (30, 30, 30), -1)
    cv2.rectangle(canvas, (10, 10), (200, 75), (70, 70, 70), 1)

    target_str = f"#{target_manager.locked_target_id}" if target_manager.locked_target_id is not None else "None"
    status_col = (0, 215, 255) if target_manager.is_locked else (180, 180, 180)

    cv2.putText(canvas, f"Tracks : {len(tracks)}", (18, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Target : {target_str} ({target_manager.status.value})", (18, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, status_col, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Hands  : {len(gestures)}", (18, 68),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1, cv2.LINE_AA)

    # Top Right: Flip / Mirror status
    flip_str = f"Flip: {'ON' if is_flipped else 'OFF'} (Key 'm')"
    cv2.putText(canvas, flip_str, (w - 180, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    # Bottom Overlay: Performance & Event status
    cv2.rectangle(canvas, (10, h - 35), (w - 10, h - 10), (25, 25, 25), -1)
    info_str = f"Speed: {fps:4.1f} FPS | Latency: {latency_ms:5.1f} ms | Status: {status_msg}"
    cv2.putText(canvas, info_str, (18, h - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

    return canvas


# =============================================================================
# 3. TopModule Application Coordinator
# =============================================================================
class TopModule:
    """
    Central Coordinator for NEXUS robot software.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        conf_threshold: float = 0.50,
        flip_horizontal: bool = True,
        target_loss_timeout: float = 3.0
    ):
        print("=" * 65)
        print("NEXUS PERSON FOLLOWER ROBOT — TOP MODULE INITIALIZATION")
        print("=" * 65)

        # 1. Initialize State Machine with 3.0s toggle cooldown
        self.state_machine = NexusStateMachine(toggle_cooldown=3.0)
        print(f"[TopModule] State Machine Initialized -> State: {self.state_machine.state.value}")

        # 2. Initialize Person Detector (YOLO)
        self.person_detector = PersonDetector(
            model_path=model_path,
            conf_threshold=conf_threshold
        )

        # 3. Initialize Multi-Person Tracker (IoU-based)
        self.tracker = PersonTracker(max_missed_frames=30, iou_threshold=0.25)
        print(f"[TopModule] Multi-Person Tracker Initialized")

        # 4. Initialize Target Lock Manager (with 3.0s automatic loss timeout)
        self.target_manager = TargetLockManager(loss_timeout_seconds=target_loss_timeout)
        print(f"[TopModule] Target Lock Manager Initialized (Loss Timeout: {target_loss_timeout:.1f}s)")

        # 5. Initialize Gesture Recognizer (MediaPipe Open Palm 🖐️ with OpenCV Face Exclusion)
        self.gesture_recognizer = GestureRecognizer(
            min_detection_confidence=0.60,
            required_consecutive_frames=2,
            cooldown_seconds=3.0
        )

        # 6. Display preferences
        self.flip_horizontal = flip_horizontal
        print(f"[TopModule] Horizontal Flip (Un-mirror): {'ENABLED' if self.flip_horizontal else 'DISABLED'}")
        print("=" * 65)

    def run(self, source: str = "0", show: bool = True, save_path: Optional[Path] = None):
        """
        Main execution loop.
        """
        is_camera = source.isdigit()
        src_id = int(source) if is_camera else source

        print(f"[TopModule] Opening video source: {source}...")
        cap = cv2.VideoCapture(src_id)

        if not cap.isOpened():
            print(f"[ERROR] Could not open video source '{source}'.")
            return

        writer = None
        if save_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            save_path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(save_path), fourcc, fps_src, (w, h))

        print("\n[TopModule] Running. Press 'q' or 'ESC' to exit, 'm' to toggle mirror flip.")
        print("            Show Open Palm (🖐️) to Lock onto target and toggle NEXUS ON/OFF.\n")

        fps_buffer = []

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                t_start = time.perf_counter()

                # Step 0: Apply horizontal flip for natural webcam view
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)

                # Step 1: Person Detection (YOLO)
                raw_persons = self.person_detector.detect(frame)

                # Step 2: Person Tracking (Maintains stable track IDs)
                tracks = self.tracker.update(raw_persons)

                # Step 3: Gesture Recognition (Open Palm 🖐️ with Face Exclusion)
                gestures = self.gesture_recognizer.detect(frame, persons=raw_persons)

                # Step 4: Target Lock Update & Loss Timeout Monitoring
                if self.state_machine.state == NexusState.ON:
                    locked_person, target_event = self.target_manager.update(tracks)
                    if target_event == TargetEvent.TARGET_LOST_TIMEOUT:
                        # TARGET LOST FOR > 3.0 SECONDS -> AUTOMATICALLY NEXUS OFF!
                        self.state_machine.force_off("Target Lost Timeout (>3.0s)")

                # Step 5: Password Gesture Handling & Association
                if self.gesture_recognizer.check_password_event(gestures):
                    pwd_gesture = next((g for g in gestures if g.is_open_palm), None)

                    if self.state_machine.state == NexusState.OFF:
                        # In OFF state: check cooldown first
                        if not self.state_machine.is_in_cooldown:
                            candidate: Optional[TrackedPerson] = None
                            if pwd_gesture and tracks:
                                candidate = self.target_manager.associate_gesture_with_person(
                                    tracks, pwd_gesture
                                )

                            if candidate is not None:
                                # Target successfully identified and locked
                                self.target_manager.lock_target(candidate.track_id, candidate)
                                self.state_machine.handle_password_gesture(
                                    reason=f"Target #{candidate.track_id} Locked"
                                )
                            elif tracks:
                                # Fallback: lock closest visible tracked person
                                candidate = tracks[0]
                                self.target_manager.lock_target(candidate.track_id, candidate)
                                self.state_machine.handle_password_gesture(
                                    reason=f"Target #{candidate.track_id} Locked"
                                )
                            else:
                                self.state_machine.status_message = "Password seen, but no person detected to lock!"
                                print("\n[TopModule] Password seen, but no person detected to lock.")

                    elif self.state_machine.state == NexusState.ON:
                        # In ON state: Anti-hijack verification
                        if not self.state_machine.is_in_cooldown:
                            candidate = None
                            if pwd_gesture and tracks:
                                candidate = self.target_manager.associate_gesture_with_person(
                                    tracks, pwd_gesture
                                )

                            # Verify if the gesture comes from the locked target
                            if candidate and candidate.track_id == self.target_manager.locked_target_id:
                                self.target_manager.unlock_target()
                                self.state_machine.handle_password_gesture(
                                    reason="Target Deactivation Accepted"
                                )
                            elif self.target_manager.locked_target_id is None:
                                # Target wasn't locked, allow turning off
                                self.target_manager.unlock_target()
                                self.state_machine.handle_password_gesture(
                                    reason="Deactivation Accepted"
                                )
                            else:
                                hijack_id = candidate.track_id if candidate else "Unknown"
                                self.state_machine.status_message = (
                                    f"⛔ Rejected: Hand from #{hijack_id}, not Target #{self.target_manager.locked_target_id}!"
                                )
                                print(f"\n[TopModule] ⛔ Deactivation rejected: Hand belongs to Person #{hijack_id}, not Target #{self.target_manager.locked_target_id}!")

                # Step 6: Telemetry & Benchmark
                t_latency = (time.perf_counter() - t_start) * 1000.0
                fps_val = 1000.0 / t_latency if t_latency > 0 else 0.0
                fps_buffer.append(fps_val)
                if len(fps_buffer) > 30:
                    fps_buffer.pop(0)
                avg_fps = sum(fps_buffer) / len(fps_buffer)

                # Step 7: Render Composite HUD
                annotated_frame = draw_top_module_hud(
                    frame=frame,
                    state=self.state_machine.state,
                    tracks=tracks,
                    gestures=gestures,
                    target_manager=self.target_manager,
                    status_msg=self.state_machine.status_message,
                    latency_ms=t_latency,
                    fps=avg_fps,
                    is_flipped=self.flip_horizontal,
                    cooldown_remaining=self.state_machine.cooldown_remaining
                )

                # Terminal telemetry log
                target_str = f"#{self.target_manager.locked_target_id}" if self.target_manager.locked_target_id else "None"
                term_msg = (
                    f"\r[{self.state_machine.state.value}] Target: {target_str} ({self.target_manager.status.value}) | "
                    f"Tracks: {len(tracks)} | Hands: {len(gestures)} | Latency: {t_latency:5.1f} ms | FPS: {avg_fps:4.1f}"
                )
                sys.stdout.write(term_msg)
                sys.stdout.flush()

                if writer:
                    writer.write(annotated_frame)

                if show:
                    cv2.imshow("NEXUS — Top Module", annotated_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in [ord("q"), 27]:  # 'q' or ESC
                        print("\n[TopModule] Termination requested by user.")
                        break
                    elif key in [ord("m"), ord("M")]:
                        self.flip_horizontal = not self.flip_horizontal
                        print(f"\n[Mirror Toggle] Flip: {'ENABLED' if self.flip_horizontal else 'DISABLED'}")
                    elif key in [ord("t"), ord("T"), ord("p"), ord("P")]:
                        # Manual password toggle event (Press 'p' or 't')
                        if self.state_machine.state == NexusState.OFF:
                            if tracks:
                                self.target_manager.lock_target(tracks[0].track_id, tracks[0])
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")
                        else:
                            self.target_manager.unlock_target()
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")

        except KeyboardInterrupt:
            print("\n[TopModule] KeyboardInterrupt caught.")
        finally:
            cap.release()
            if writer:
                writer.release()
            if show:
                cv2.destroyAllWindows()
            print("\n[TopModule] Pipeline stopped cleanly.")


# =============================================================================
# 4. CLI Entry Point
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="NEXUS Person Follower Robot — Central Top Module",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--source", "-s", type=str, default="0",
        help="Input video source: webcam index ('0') or video file path"
    )
    parser.add_argument(
        "--model", "-m", type=str, default=None,
        help="Custom YOLO model path (.onnx or .pt). Defaults to models/yolo/exports/nexus_person_detector.onnx"
    )
    parser.add_argument(
        "--conf", type=float, default=0.50,
        help="Person detection confidence threshold"
    )
    parser.add_argument(
        "--loss-timeout", type=float, default=3.0,
        help="Timeout in seconds before target loss triggers NEXUS OFF"
    )
    parser.add_argument(
        "--no-flip", action="store_true",
        help="Disable horizontal flip (keep raw camera sensor orientation)"
    )
    parser.add_argument(
        "--no-view", action="store_true",
        help="Run headless without opening a GUI window"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Optional path to save annotated video output (.mp4)"
    )

    args = parser.parse_args()

    app = TopModule(
        model_path=Path(args.model) if args.model else None,
        conf_threshold=args.conf,
        flip_horizontal=not args.no_flip,
        target_loss_timeout=args.loss_timeout
    )

    save_target = Path(args.save) if args.save else None
    app.run(
        source=args.source,
        show=not args.no_view,
        save_path=save_target
    )


if __name__ == "__main__":
    main()
