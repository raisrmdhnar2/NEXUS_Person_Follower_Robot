#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Central Top Module (top_module.py)
=================================================================
File: top_module.py (Application Coordinator)
Adheres to:
- docs/revision/revision_concept.md
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
    6. Follow Controller / Steering Evaluator (follow_controller.py)
       - Evaluates target dx with ±0.15 deadzone -> produces ('-', 'x', '+', 's')
    7. ESP32 UART Serial Bridge (esp32_uart.py)
       - Transmits 1-byte command to ESP32 motor controller (with simulation fallback)
    8. State Machine Coordination (NexusStateMachine)
    9. Composite HUD & Telemetry Visualization (with UART Command Badge)

Usage:
    python3 top_module.py
    python3 top_module.py --source 0
    python3 top_module.py --port /dev/ttyUSB0
    python3 top_module.py --no-uart  (run without serial hardware)
"""

import argparse
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import NEXUS perception, target, control, communication, and UI modules
from raspberry_pi.vision.person_detection import PersonDetection, PersonDetector
from raspberry_pi.vision.gesture_recognition import GestureDetection, GestureRecognizer
from raspberry_pi.vision.threaded_camera import ThreadedCamera
from raspberry_pi.target.locking_target import (
    FastVisualTracker,
    PersonTracker,
    TargetLockManager,
    TrackedPerson,
    TargetStatus,
    TargetEvent,
    draw_target_overlay
)
from raspberry_pi.control.follow_controller import FollowController, SteeringCommand
from raspberry_pi.communication.esp32_uart import Esp32UartBridge
from raspberry_pi.ui.speech_manager import SpeechManager, VoiceEvent
from raspberry_pi.ui.greeting_manager import GreetingManager
from raspberry_pi.ui.face_display import FaceDisplayManager, DisplayMode, FaceExpression


# =============================================================================
# 1. State Machine Definitions
# =============================================================================
class NexusState(Enum):
    """
    Operating states for NEXUS robot.
    Matches docs/2_system_design/state_machine.md.
    """
    OFF = "Nexus Off"
    GREETING = "Greeting"
    ON = "Nexus On"


class NexusStateMachine:
    """
    State machine coordinator for NEXUS.
    Manages transitions between 'Nexus Off', 'Greeting', and 'Nexus On'.
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

    def start_greeting(self, reason: str = "Visitor Detected") -> bool:
        """Transitions from OFF to GREETING when a visitor is detected."""
        if self.state == NexusState.OFF:
            self.state = NexusState.GREETING
            self.status_message = f"{reason} -> Greeting Visitor..."
            print(f"\n[STATE TRANSITION] >>> GREETING <<< ({reason})")
            return True
        return False

    def finish_greeting(self) -> bool:
        """Transitions from GREETING back to OFF when greeting speech finishes."""
        if self.state == NexusState.GREETING:
            self.state = NexusState.OFF
            self.status_message = "Greeting Finished. Standby: Nexus Off"
            print(f"\n[STATE TRANSITION] >>> NEXUS OFF <<< (Greeting Finished)")
            return True
        return False

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
        Transitions from OFF/GREETING -> ON, or from ON -> OFF.
        Enforces toggle cooldown to prevent rapid state flickering.
        """
        now = time.time()
        if (now - self.last_transition_time) < self.toggle_cooldown:
            return False

        self.last_transition_time = now
        self.transition_count += 1

        if self.state in [NexusState.OFF, NexusState.GREETING]:
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
    steering_cmd: SteeringCommand,
    uart_status: str,
    status_msg: str,
    latency_ms: float,
    fps: float,
    is_flipped: bool,
    cooldown_remaining: float = 0.0
) -> np.ndarray:
    """
    Renders a minimalist top module HUD displaying only 'Nexus' and 'On/Off'.
    """
    canvas = frame.copy()
    h, w = canvas.shape[:2]

    # Draw minimalist bounding box for locked target or detected persons
    if target_manager.locked_person is not None:
        px1, py1, px2, py2 = target_manager.locked_person.bbox
        # Neon Green box for locked target
        cv2.rectangle(canvas, (px1, py1), (px2, py2), (0, 255, 100), 2)
    elif tracks:
        for t in tracks:
            tx1, ty1, tx2, ty2 = t.bbox
            cv2.rectangle(canvas, (tx1, ty1), (tx2, ty2), (180, 180, 180), 1)

    # -------------------------------------------------------------------------
    # Minimalist Badge: "NEXUS" & "ON / OFF"
    # -------------------------------------------------------------------------
    is_on = (state == NexusState.ON)
    badge_w, badge_h = 240, 84
    bx1 = (w - badge_w) // 2
    by1 = 16
    bx2 = bx1 + badge_w
    by2 = by1 + badge_h

    # Semi-transparent dark rounded/bordered background
    overlay = canvas.copy()
    cv2.rectangle(overlay, (bx1, by1), (bx2, by2), (18, 18, 22), -1)
    status_color = (0, 230, 80) if is_on else (50, 50, 240)  # Bright Green if ON, Red if OFF
    cv2.rectangle(overlay, (bx1, by1), (bx2, by2), status_color, 2)
    cv2.addWeighted(overlay, 0.75, canvas, 0.25, 0, canvas)

    # Line 1: "Nexus"
    title_text = "Nexus"
    (tw1, th1), _ = cv2.getTextSize(title_text, cv2.FONT_HERSHEY_DUPLEX, 0.75, 1)
    tx1 = bx1 + (badge_w - tw1) // 2
    ty1 = by1 + 32
    cv2.putText(canvas, title_text, (tx1, ty1),
                cv2.FONT_HERSHEY_DUPLEX, 0.75, (245, 245, 245), 1, cv2.LINE_AA)

    # Line 2: "On" or "Off"
    state_text = "On" if is_on else "Off"
    (tw2, th2), _ = cv2.getTextSize(state_text, cv2.FONT_HERSHEY_DUPLEX, 1.0, 2)
    tx2 = bx1 + (badge_w - tw2) // 2
    ty2 = by1 + 70
    cv2.putText(canvas, state_text, (tx2, ty2),
                cv2.FONT_HERSHEY_DUPLEX, 1.0, status_color, 2, cv2.LINE_AA)

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
        target_loss_timeout: float = 3.0,
        serial_port: Optional[str] = "auto",
        baudrate: int = 115200,
        no_uart: bool = False,
        deadzone: float = 0.15,
        img_size: int = 640,
        gesture_interval: int = 4,
        detect_interval: int = 1,
        sync_interval: int = 45,
        no_speech: bool = False,
        greeting_cooldown: float = 15.0,
        greeting_empty_reset: float = 5.0,
        use_threaded_cam: bool = True,
        use_mjpeg: bool = False,
        face_fullscreen: bool = False,
        display_mode: str = "face_only"
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
            conf_threshold=conf_threshold,
            img_size=img_size
        )
        self.img_size = self.person_detector.img_size
        self.use_mjpeg = use_mjpeg

        # 3. Initialize Multi-Person Tracker (IoU-based)
        self.tracker = PersonTracker(max_missed_frames=150, iou_threshold=0.25)
        print(f"[TopModule] Multi-Person Tracker Initialized")

        # 4. Initialize Target Lock Manager (with loss timeout)
        self.target_manager = TargetLockManager(loss_timeout_seconds=target_loss_timeout)
        print(f"[TopModule] Target Lock Manager Initialized (Loss Timeout: {target_loss_timeout:.1f}s)")

        # 4.5 Initialize Fast Visual Object Tracker (OpenCV KCF/CSRT)
        self.visual_tracker = FastVisualTracker()
        print(f"[TopModule] Fast Visual Tracker Initialized (OpenCV KCF/CSRT)")

        # 5. Initialize Follow Controller (Deadzone ±0.15 for -, x, + steering)
        self.follow_controller = FollowController(deadzone=deadzone)
        print(f"[TopModule] Follow Controller Initialized (Deadzone: ±{deadzone*100:.0f}%)")

        # 6. Initialize ESP32 UART Serial Bridge
        self.uart_bridge = Esp32UartBridge(
            port=serial_port,
            baudrate=baudrate,
            enabled=not no_uart
        )
        print(f"[TopModule] UART Bridge: {self.uart_bridge.status_label}")

        # 6.5 Initialize Speech and Audio Manager (JARVIS voice)
        self.speech_manager = SpeechManager(enabled=not no_speech)

        # 6.6 Initialize Greeting Manager (3-layer anti-spam)
        self.greeting_manager = GreetingManager(
            cooldown_seconds=greeting_cooldown,
            empty_reset_seconds=greeting_empty_reset
        )
        self._greeting_finished_flag = False

        # 6.7 Initialize Expressive Face Display (Fullscreen & Animated Emoji UI)
        disp_enum = DisplayMode.FACE_ONLY
        try:
            disp_enum = DisplayMode(display_mode.lower())
        except Exception:
            pass

        self.face_display = FaceDisplayManager(
            window_name="NEXUS — Expressive Face UI",
            width=1024,
            height=600,
            fullscreen=face_fullscreen,
            display_mode=disp_enum
        )
        self._last_reacquire_time = 0.0
        self._last_deactivate_time = 0.0
        print(f"[TopModule] Expressive Face UI Initialized -> Mode: {disp_enum.value.upper()} | Fullscreen: {'ENABLED' if face_fullscreen else 'WINDOWED'}")

        # Periodic check-in timing while following
        self.last_following_checkin = 0.0
        self.following_checkin_interval = 45.0  # seconds

        # 7. Initialize Gesture Recognizer (MediaPipe Victory Sign ✌️ with OpenCV Face Exclusion)
        self.gesture_recognizer = GestureRecognizer(
            min_detection_confidence=0.60,
            required_consecutive_frames=2,
            cooldown_seconds=3.0
        )

        # 8. High-speed pipeline preferences
        self.flip_horizontal = flip_horizontal
        self.gesture_interval = max(1, int(gesture_interval))
        self.detect_interval = max(1, int(detect_interval))
        self.sync_interval = max(0, int(sync_interval))
        self.use_threaded_cam = use_threaded_cam

        print(f"[TopModule] Horizontal Flip (Un-mirror): {'ENABLED' if self.flip_horizontal else 'DISABLED'}")
        print(f"[TopModule] High-Speed Pipeline -> Resolution: {self.img_size}x{self.img_size} | "
              f"Gesture Interval: Every {self.gesture_interval} frames | "
              f"Tracker: FastVisualTracker (OpenCV ~2-4ms) | "
              f"Audio / Speech: {'ENABLED' if not no_speech else 'MUTED'}")
        print("=" * 65)

    def _on_greeting_complete(self):
        """Thread-safe callback invoked when startup greeting audio finishes."""
        self._greeting_finished_flag = True

    def _determine_face_expression(self, target_event: TargetEvent) -> Tuple[FaceExpression, str]:
        """
        Maps current NexusState, TargetEvent, and target status to a FaceExpression
        according to docs/ui.md.
        """
        now = time.time()
        # 1. Target Reacquired transient expression (1.5 seconds)
        if target_event == TargetEvent.TARGET_REACQUIRED or (now - self._last_reacquire_time) < 1.5:
            return FaceExpression.RELIEVED, "TARGET REACQUIRED // WELCOME BACK"

        # 2. State-driven expressions
        if self.state_machine.state == NexusState.ON:
            if self.target_manager.status == TargetStatus.LOST:
                time_left = self.target_manager.time_until_timeout
                return FaceExpression.SEARCHING, f"TARGET LOST // SEARCHING ({time_left:3.1f}s)"
            else:
                tid = self.target_manager.locked_target_id or "?"
                return FaceExpression.FOLLOWING, f"NEXUS ON // FOLLOWING TARGET #{tid}"

        elif self.state_machine.state == NexusState.GREETING:
            return FaceExpression.GREETING, "GREETING VISITOR // JARVIS VOICE"

        else:
            # NexusState.OFF
            if (now - self._last_deactivate_time) < 2.0 or self.greeting_manager.require_scene_clear:
                return FaceExpression.GOODBYE, "DEACTIVATED // SEE YOU LATER"
            return FaceExpression.IDLE, "STANDBY // READY FOR VISITOR"

    def run(self, source: str = "0", show: bool = True, save_path: Optional[Path] = None):
        """
        Main execution loop.
        """
        is_camera = source.isdigit()
        src_id = int(source) if is_camera else source

        # Initialize Video Source (ThreadedCamera for USB/CSI cameras to eliminate lag)
        if is_camera and self.use_threaded_cam:
            codec_str = "MJPG" if self.use_mjpeg else "YUYV"
            print(f"[TopModule] Initializing High-Speed Threaded Camera on source '{source}' ({codec_str} 640x480 @ 30 FPS)...")
            cap = ThreadedCamera(
                source=src_id,
                width=640,
                height=480,
                fps=30,
                use_mjpeg=self.use_mjpeg
            ).start()
        else:
            print(f"[TopModule] Opening standard video source: {source}...")
            cap = cv2.VideoCapture(src_id)

        is_opened = cap.is_opened() if hasattr(cap, "is_opened") else cap.isOpened()
        if not is_opened:
            print(f"[ERROR] Could not open video source '{source}'.")
            return

        writer = None
        if save_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            fps_src = cap.get(cv2.CAP_PROP_FPS) if hasattr(cap, "get") else 30.0
            fps_src = fps_src or 30.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if hasattr(cap, "get") else 640
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if hasattr(cap, "get") else 480
            save_path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(save_path), fourcc, fps_src, (w, h))

        print("\n[TopModule] Running (30 FPS Decoupled Pipeline).")
        print("            Press 'q' or 'ESC' to exit, 'm' to toggle mirror flip.")
        print("            Show Victory Sign (✌️) to Lock onto target and toggle NEXUS ON/OFF.\n")

        fps_buffer = []
        frame_idx = 0
        last_raw_persons: List[PersonDetection] = []
        last_gestures: List[GestureDetection] = []

        try:
            while (cap.is_opened() if hasattr(cap, "is_opened") else cap.isOpened()):
                ret, frame = cap.read()
                if not ret or frame is None:
                    if is_camera:
                        time.sleep(0.005)
                        continue
                    break

                t_start = time.perf_counter()

                # Process asynchronous audio completion flags in main thread
                if self._greeting_finished_flag:
                    self._greeting_finished_flag = False
                    self.greeting_manager.finish_greeting()
                    if self.state_machine.state == NexusState.GREETING:
                        self.state_machine.finish_greeting()

                # Step 0: Apply horizontal flip for natural webcam view
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)

                frame_h, frame_w = frame.shape[:2]
                target_event = TargetEvent.NONE

                # Step 1, 2 & 3: State-Driven Perception Pipeline
                if self.state_machine.state == NexusState.ON:
                    # =========================================================
                    # [PILLAR 1] NEXUS ON: FAST VISUAL TRACKER PIPELINE (~2-4ms)
                    # =========================================================
                    track_ok = False
                    tracked_bbox = None
                    if self.visual_tracker.is_tracking:
                        track_ok, tracked_bbox = self.visual_tracker.update(frame)

                    need_yolo_sync = (
                        (not track_ok)
                        or (self.target_manager.status == TargetStatus.LOST)
                        or (self.sync_interval > 0 and frame_idx % self.sync_interval == 0)
                    )

                    if need_yolo_sync:
                        raw_persons = self.person_detector.detect(frame)
                        last_raw_persons = raw_persons
                        tracks = self.tracker.update(raw_persons)
                        locked_person, target_event = self.target_manager.update(tracks)

                        if self.target_manager.is_target_present and self.target_manager.locked_person is not None:
                            self.visual_tracker.start_track(frame, self.target_manager.locked_person.bbox)
                            if target_event == TargetEvent.TARGET_REACQUIRED:
                                self._last_reacquire_time = time.time()
                                self.speech_manager.stop()
                                self.speech_manager.speak_target_locked()
                                print(f"\n[TopModule] 🎯 Target #{self.target_manager.locked_target_id} re-acquired! Resuming tracking.")
                        elif target_event == TargetEvent.TARGET_LOST:
                            # Target temporarily lost -> Stop visual tracker to prevent background lock!
                            self.visual_tracker.stop()
                            self.speech_manager.speak_target_lost()
                        elif target_event == TargetEvent.TARGET_LOST_TIMEOUT:
                            # Target missing beyond grace period -> Speech: "I can't find you." -> NEXUS OFF!
                            self.visual_tracker.stop()
                            self.target_manager.unlock_target()
                            self.greeting_manager.on_deactivation()
                            self._last_deactivate_time = time.time()
                            self.speech_manager.speak_target_timeout()
                            self.state_machine.force_off("Target Lost Timeout")
                    else:
                        # High-speed tracking path (~2-4 ms compute time)
                        if self.target_manager.locked_person is not None and tracked_bbox is not None:
                            self.target_manager.locked_person.bbox = tracked_bbox
                            self.target_manager.locked_person.last_seen_timestamp = time.time()
                            self.target_manager.locked_person.missed_frames = 0
                            self.target_manager.status = TargetStatus.LOCKED
                            self.target_manager.last_seen_time = time.time()
                            self.target_manager.loss_start_time = None
                            tracks = [self.target_manager.locked_person]
                        else:
                            tracks = []

                    # Periodic Following Check-in ("I'm right behind you.")
                    now_t = time.time()
                    if self.target_manager.is_target_present and (now_t - self.last_following_checkin) >= self.following_checkin_interval:
                        self.last_following_checkin = now_t
                        self.speech_manager.speak_following()

                    # =========================================================
                    # [PILLAR 2] FAST CROP-ROI MEDIAPIPE GESTURE RECOGNITION (~15ms)
                    # =========================================================
                    if frame_idx % self.gesture_interval == 0:
                        if self.target_manager.is_target_present and self.target_manager.locked_person is not None:
                            gestures = self.gesture_recognizer.detect_roi(
                                frame, self.target_manager.locked_person.bbox
                            )
                        else:
                            gestures = []
                        last_gestures = gestures
                    else:
                        gestures = last_gestures

                    # Check Deactivation Password Gesture (✌️ Victory Sign from target)
                    if self.gesture_recognizer.check_password_event(gestures):
                        pwd_gesture = next((g for g in gestures if (getattr(g, "is_victory", False) or g.is_open_palm)), None)
                        if pwd_gesture is not None and not self.state_machine.is_in_cooldown:
                            self.visual_tracker.stop()
                            self.target_manager.unlock_target()
                            self.greeting_manager.on_deactivation()
                            self._last_deactivate_time = time.time()
                            self.speech_manager.speak_deactivation()
                            self.state_machine.handle_password_gesture(
                                reason="Target Deactivation Accepted"
                            )

                else:
                    # =========================================================
                    # NEXUS OFF / GREETING: SCANNING / DETECTION PIPELINE
                    # =========================================================
                    # Step 1: Person Detection (YOLO with detect_interval)
                    if frame_idx % self.detect_interval == 0:
                        raw_persons = self.person_detector.detect(frame)
                        last_raw_persons = raw_persons
                    else:
                        raw_persons = last_raw_persons

                    # Step 2: Multi-Person Tracking (IoU-based)
                    tracks = self.tracker.update(raw_persons)

                    # Step 3: Full-Frame Gesture Recognition (sampled with gesture_interval)
                    if frame_idx % self.gesture_interval == 0:
                        gestures = self.gesture_recognizer.detect(frame, persons=raw_persons)
                        last_gestures = gestures
                    else:
                        gestures = last_gestures

                    # Step 4: Visitor Greeting Check (3-Layer Anti-Spam)
                    if self.state_machine.state == NexusState.OFF:
                        should_greet, cand_id = self.greeting_manager.evaluate(
                            tracks,
                            is_off_state=True,
                            is_speaking=self.speech_manager.is_speaking
                        )
                        if should_greet and cand_id is not None:
                            self.greeting_manager.mark_greeted(cand_id)
                            self.state_machine.start_greeting(reason=f"Visitor #{cand_id} Detected")
                            self.speech_manager.speak_greeting(on_complete=self._on_greeting_complete)

                    # Step 5: Activation Password Gesture Check (✌️ Victory Sign to Lock & Follow)
                    if self.gesture_recognizer.check_password_event(gestures):
                        pwd_gesture = next((g for g in gestures if (getattr(g, "is_victory", False) or g.is_open_palm)), None)
                        if not self.state_machine.is_in_cooldown:
                            candidate: Optional[TrackedPerson] = None
                            if pwd_gesture and tracks:
                                candidate = self.target_manager.associate_gesture_with_person(
                                    tracks, pwd_gesture
                                )

                            if candidate is not None:
                                self.speech_manager.stop()
                                self.greeting_manager.finish_greeting()
                                self.greeting_manager.mark_interacted(candidate.track_id)
                                self.target_manager.lock_target(candidate.track_id, candidate)
                                self.visual_tracker.start_track(frame, candidate.bbox)
                                self.state_machine.handle_password_gesture(
                                    reason=f"Target #{candidate.track_id} Locked"
                                )
                                self.speech_manager.speak_activation()
                                self.last_following_checkin = time.time()
                            elif tracks:
                                candidate = tracks[0]
                                self.speech_manager.stop()
                                self.greeting_manager.finish_greeting()
                                self.greeting_manager.mark_interacted(candidate.track_id)
                                self.target_manager.lock_target(candidate.track_id, candidate)
                                self.visual_tracker.start_track(frame, candidate.bbox)
                                self.state_machine.handle_password_gesture(
                                    reason=f"Target #{candidate.track_id} Locked"
                                )
                                self.speech_manager.speak_activation()
                                self.last_following_checkin = time.time()
                            else:
                                self.state_machine.status_message = "Password seen, but no person detected to lock!"
                                print("\n[TopModule] Password seen, but no person detected to lock.")

                frame_idx += 1

                # Step 6: Follow Control & ESP32 UART Transmission
                current_target = (
                    self.target_manager.locked_person
                    if self.target_manager.is_target_present
                    else None
                )
                steering_cmd = self.follow_controller.evaluate(
                    is_active=(self.state_machine.state == NexusState.ON),
                    target_manager=self.target_manager,
                    target_person=current_target,
                    frame_width=frame_w
                )
                target_dx = self.follow_controller.last_dx
                is_active = (self.state_machine.state == NexusState.ON) and (self.target_manager.is_target_present)
                self.uart_bridge.send_command(is_active=is_active, dx=target_dx)

                # Step 7: Telemetry & Benchmark
                t_latency = (time.perf_counter() - t_start) * 1000.0
                fps_val = 1000.0 / t_latency if t_latency > 0 else 0.0
                fps_buffer.append(fps_val)
                if len(fps_buffer) > 30:
                    fps_buffer.pop(0)
                avg_fps = sum(fps_buffer) / len(fps_buffer)

                # Step 8: Render Composite HUD
                annotated_frame = draw_top_module_hud(
                    frame=frame,
                    state=self.state_machine.state,
                    tracks=tracks,
                    gestures=gestures,
                    target_manager=self.target_manager,
                    steering_cmd=steering_cmd,
                    uart_status=self.uart_bridge.status_label,
                    status_msg=self.state_machine.status_message,
                    latency_ms=t_latency,
                    fps=avg_fps,
                    is_flipped=self.flip_horizontal,
                    cooldown_remaining=self.state_machine.cooldown_remaining
                )

                # Terminal telemetry log
                state_str = "ON" if self.state_machine.state == NexusState.ON else "OFF"
                target_str = f"#{self.target_manager.locked_target_id}" if self.target_manager.locked_target_id else "None"
                term_msg = (
                    f"\r[Nexus {state_str}] Target: {target_str} | "
                    f"UART Sent: '{self.uart_bridge.last_command}' | "
                    f"FPS: {avg_fps:4.1f} | Latency: {t_latency:4.1f}ms "
                )
                sys.stdout.write(term_msg)
                sys.stdout.flush()

                if writer:
                    writer.write(annotated_frame)

                if show:
                    expr, face_status = self._determine_face_expression(target_event)
                    key = self.face_display.show(
                        expression=expr,
                        status_label=face_status,
                        is_speaking=self.speech_manager.is_speaking,
                        steering_cmd=steering_cmd.value,
                        camera_frame=annotated_frame
                    )
                    if key in [ord("q"), 27]:  # 'q' or ESC
                        print("\n[TopModule] Termination requested by user.")
                        break
                    elif key in [ord("m"), ord("M")]:
                        self.flip_horizontal = not self.flip_horizontal
                        print(f"\n[Mirror Toggle] Flip: {'ENABLED' if self.flip_horizontal else 'DISABLED'}")
                    elif key in [ord("t"), ord("T"), ord("p"), ord("P")]:
                        # Manual password toggle event (Press 'p' or 't')
                        if self.state_machine.state in [NexusState.OFF, NexusState.GREETING]:
                            if tracks:
                                self.speech_manager.stop()
                                self.greeting_manager.finish_greeting()
                                self.greeting_manager.mark_interacted(tracks[0].track_id)
                                self.target_manager.lock_target(tracks[0].track_id, tracks[0])
                                self.visual_tracker.start_track(frame, tracks[0].bbox)
                            self.speech_manager.speak_activation()
                            self.last_following_checkin = time.time()
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")
                        else:
                            self.visual_tracker.stop()
                            self.target_manager.unlock_target()
                            self.greeting_manager.on_deactivation()
                            self._last_deactivate_time = time.time()
                            self.speech_manager.speak_deactivation()
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")
                    elif key in [ord("u"), ord("U")]:
                        # Manual target unlock (Press 'u')
                        self.visual_tracker.stop()
                        self.target_manager.unlock_target()
                        self.greeting_manager.on_deactivation()
                        self._last_deactivate_time = time.time()
                        self.speech_manager.speak_deactivation()
                        if self.state_machine.state == NexusState.ON:
                            self.state_machine.force_off("Manual Target Unlock")

        except KeyboardInterrupt:
            print("\n[TopModule] KeyboardInterrupt caught.")
        finally:
            if hasattr(self, "face_display"):
                self.face_display.close()
            if hasattr(self, "visual_tracker"):
                self.visual_tracker.stop()
            if hasattr(self, "speech_manager"):
                self.speech_manager.stop()
            if hasattr(cap, "stop"):
                cap.stop()
            elif hasattr(cap, "release"):
                cap.release()
            self.uart_bridge.close()
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
        "--imgsz", type=int, default=640,
        help="YOLO inference resolution (default 640 for nexus_person_detector.onnx, or 320 for 30 FPS Raspberry Pi speed)"
    )
    parser.add_argument(
        "--conf", type=float, default=0.45,
        help="Person detection confidence threshold (default 0.45 for responsive re-acquisition)"
    )
    parser.add_argument(
        "--gesture-interval", type=int, default=4,
        help="Execute MediaPipe gesture recognition every N frames to save CPU (default 4)"
    )
    parser.add_argument(
        "--detect-interval", type=int, default=1,
        help="Execute YOLO person detection every N frames (default 1; set 2 for even higher FPS)"
    )
    parser.add_argument(
        "--sync-interval", type=int, default=45,
        help="Frames between YOLO drift-correction checks during tracking (default 45; set 0 for on-loss only)"
    )
    parser.add_argument(
        "--no-speech", action="store_true",
        help="Mute audio dialogue playback (run speech in simulation mode)"
    )
    parser.add_argument(
        "--greeting-cooldown", type=float, default=15.0,
        help="Minimum cooldown time (seconds) between visitor startup greetings (Layer 3)"
    )
    parser.add_argument(
        "--greeting-empty-reset", type=float, default=5.0,
        help="Duration (seconds) camera must be empty to reset greeted memory for new visitors (Layer 2)"
    )
    parser.add_argument(
        "--no-threaded-cam", action="store_true",
        help="Disable asynchronous threaded camera and use standard blocking VideoCapture"
    )
    parser.add_argument(
        "--mjpeg", action="store_true",
        help="Request MJPEG camera codec instead of clean uncompressed YUYV (use only if camera requires it)"
    )
    parser.add_argument(
        "--loss-timeout", type=float, default=4.0,
        help="Timeout in seconds before target loss triggers NEXUS OFF (default 4.0s)"
    )
    parser.add_argument(
        "--deadzone", type=float, default=0.15,
        help="Steering deadzone ratio (+/- from center)"
    )
    parser.add_argument(
        "--port", type=str, default="auto",
        help="ESP32 serial port (e.g. /dev/ttyUSB0, /dev/ttyACM0, or 'auto')"
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="ESP32 UART serial baudrate"
    )
    parser.add_argument(
        "--no-uart", action="store_true",
        help="Disable physical UART serial and force simulation mode"
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
    parser.add_argument(
        "--fullscreen", "-f", action="store_true",
        help="Launch the Robot Face UI in Fullsize / Fullscreen mode (docs/ui.md)"
    )
    parser.add_argument(
        "--display-mode", type=str, default="face_only",
        choices=["face_only", "face_pip", "camera_hud"],
        help="Initial screen display mode: 'face_only' (clean robot face), 'face_pip' (face + camera PiP), or 'camera_hud' (developer HUD)"
    )

    args = parser.parse_args()

    app = TopModule(
        model_path=Path(args.model) if args.model else None,
        conf_threshold=args.conf,
        flip_horizontal=not args.no_flip,
        target_loss_timeout=args.loss_timeout,
        serial_port=args.port,
        baudrate=args.baud,
        no_uart=args.no_uart,
        deadzone=args.deadzone,
        img_size=args.imgsz,
        gesture_interval=args.gesture_interval,
        detect_interval=args.detect_interval,
        sync_interval=args.sync_interval,
        no_speech=args.no_speech,
        greeting_cooldown=args.greeting_cooldown,
        greeting_empty_reset=args.greeting_empty_reset,
        use_threaded_cam=not args.no_threaded_cam,
        use_mjpeg=args.mjpeg,
        face_fullscreen=args.fullscreen,
        display_mode=args.display_mode
    )

    save_target = Path(args.save) if args.save else None
    app.run(
        source=args.source,
        show=not args.no_view,
        save_path=save_target
    )


if __name__ == "__main__":
    main()
