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
from typing import List, Optional

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import NEXUS perception, target, control, and communication modules
from raspberry_pi.vision.person_detection import PersonDetection, PersonDetector
from raspberry_pi.vision.gesture_recognition import GestureDetection, GestureRecognizer
from raspberry_pi.vision.threaded_camera import ThreadedCamera
from raspberry_pi.target.locking_target import (
    PersonTracker,
    TargetLockManager,
    TrackedPerson,
    TargetStatus,
    TargetEvent,
    draw_target_overlay
)
from raspberry_pi.control.follow_controller import FollowController, SteeringCommand
from raspberry_pi.communication.esp32_uart import Esp32UartBridge


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
    steering_cmd: SteeringCommand,
    uart_status: str,
    status_msg: str,
    latency_ms: float,
    fps: float,
    is_flipped: bool,
    cooldown_remaining: float = 0.0
) -> np.ndarray:
    """
    Renders top module HUD with Target Locking, Hand Gestures,
    Master State Banner, Steering Command Badge, and system telemetry.
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
    banner_w, banner_h = 380, 52
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
    sty = by1 + 45
    cv2.putText(canvas, sub_text, (stx, sty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (235, 235, 235), 1, cv2.LINE_AA)

    # -------------------------------------------------------------------------
    # D. Steering Command Badge (ESP32 UART Output Indicator)
    # -------------------------------------------------------------------------
    cmd_w, cmd_h = 240, 28
    cx1 = (w - cmd_w) // 2
    cy1 = by2 + 6
    cx2 = cx1 + cmd_w
    cy2 = cy1 + cmd_h

    # Select color & icon based on active command
    if steering_cmd == SteeringCommand.LEFT:
        cmd_bg = (0, 140, 255)       # Amber/Orange for Left
        cmd_text = "◄◄ BELOK KIRI [-]"
    elif steering_cmd == SteeringCommand.RIGHT:
        cmd_bg = (0, 140, 255)       # Amber/Orange for Right
        cmd_text = "BELOK KANAN [+] ►►"
    elif steering_cmd == SteeringCommand.CENTER:
        cmd_bg = (0, 180, 0)         # Vibrant Green for Center
        cmd_text = "▲ TARGET CENTER [x] ▲"
    else:
        cmd_bg = (45, 45, 45)         # Dark Gray for Stop
        cmd_text = "■ MOTOR STOP [s] ■"

    cv2.rectangle(canvas, (cx1, cy1), (cx2, cy2), cmd_bg, -1)
    cv2.rectangle(canvas, (cx1, cy1), (cx2, cy2), (220, 220, 220), 1)

    (ctw, cth), cbl = cv2.getTextSize(cmd_text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 2)
    ctx = cx1 + (cmd_w - ctw) // 2
    cty = cy1 + (cmd_h + cth) // 2 - 2
    cv2.putText(canvas, cmd_text, (ctx, cty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2, cv2.LINE_AA)

    # -------------------------------------------------------------------------
    # E. Telemetry & Counters
    # -------------------------------------------------------------------------
    # Top Left: Perception & Target Status Box
    cv2.rectangle(canvas, (10, 10), (220, 80), (30, 30, 30), -1)
    cv2.rectangle(canvas, (10, 10), (220, 80), (70, 70, 70), 1)

    target_str = f"#{target_manager.locked_target_id}" if target_manager.locked_target_id is not None else "None"
    status_col = (0, 215, 255) if target_manager.is_locked else (180, 180, 180)

    cv2.putText(canvas, f"Tracks : {len(tracks)}", (18, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Target : {target_str} ({target_manager.status.value})", (18, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, status_col, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"UART   : {uart_status[:18]}", (18, 68),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 220, 255), 1, cv2.LINE_AA)

    # Top Right: Flip / Mirror status
    flip_str = f"Flip: {'ON' if is_flipped else 'OFF'} (Key 'm')"
    cv2.putText(canvas, flip_str, (w - 180, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    # Bottom Overlay: Performance & Event status
    cv2.rectangle(canvas, (10, h - 35), (w - 10, h - 10), (25, 25, 25), -1)
    info_str = f"Speed: {fps:4.1f} FPS | Latency: {latency_ms:5.1f} ms | UART CMD: [{steering_cmd.value}] | Status: {status_msg}"
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
        target_loss_timeout: float = 3.0,
        serial_port: Optional[str] = "auto",
        baudrate: int = 115200,
        no_uart: bool = False,
        deadzone: float = 0.15,
        img_size: int = 640,
        gesture_interval: int = 4,
        detect_interval: int = 1,
        use_threaded_cam: bool = True
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

        # 3. Initialize Multi-Person Tracker (IoU-based)
        self.tracker = PersonTracker(max_missed_frames=30, iou_threshold=0.25)
        print(f"[TopModule] Multi-Person Tracker Initialized")

        # 4. Initialize Target Lock Manager (with 3.0s automatic loss timeout)
        self.target_manager = TargetLockManager(loss_timeout_seconds=target_loss_timeout)
        print(f"[TopModule] Target Lock Manager Initialized (Loss Timeout: {target_loss_timeout:.1f}s)")

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

        # 7. Initialize Gesture Recognizer (MediaPipe Open Palm 🖐️ with OpenCV Face Exclusion)
        self.gesture_recognizer = GestureRecognizer(
            min_detection_confidence=0.60,
            required_consecutive_frames=2,
            cooldown_seconds=3.0
        )

        # 8. High-speed pipeline preferences
        self.flip_horizontal = flip_horizontal
        self.gesture_interval = max(1, int(gesture_interval))
        self.detect_interval = max(1, int(detect_interval))
        self.use_threaded_cam = use_threaded_cam

        print(f"[TopModule] Horizontal Flip (Un-mirror): {'ENABLED' if self.flip_horizontal else 'DISABLED'}")
        print(f"[TopModule] High-Speed Pipeline -> Resolution: {self.img_size}x{self.img_size} | "
              f"Gesture Interval: Every {self.gesture_interval} frames | "
              f"Threaded Cam: {'ENABLED' if self.use_threaded_cam else 'DISABLED'}")
        print("=" * 65)

    def run(self, source: str = "0", show: bool = True, save_path: Optional[Path] = None):
        """
        Main execution loop.
        """
        is_camera = source.isdigit()
        src_id = int(source) if is_camera else source

        # Initialize Video Source (ThreadedCamera for USB/CSI cameras to eliminate lag)
        if is_camera and self.use_threaded_cam:
            print(f"[TopModule] Initializing High-Speed Threaded Camera on source '{source}' (MJPG 640x480 @ 30 FPS)...")
            cap = ThreadedCamera(source=src_id, width=640, height=480, fps=30).start()
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
        print("            Show Open Palm (🖐️) to Lock onto target and toggle NEXUS ON/OFF.\n")

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

                # Step 0: Apply horizontal flip for natural webcam view
                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)

                frame_h, frame_w = frame.shape[:2]

                # Step 1: Person Detection (YOLO with detect_interval)
                if frame_idx % self.detect_interval == 0:
                    raw_persons = self.person_detector.detect(frame)
                    last_raw_persons = raw_persons
                else:
                    raw_persons = last_raw_persons

                # Step 2: Person Tracking (Runs on every frame at full 30 FPS)
                tracks = self.tracker.update(raw_persons)

                # Step 3: Gesture Recognition (Smart Sampling with gesture_interval)
                if frame_idx % self.gesture_interval == 0:
                    gestures = self.gesture_recognizer.detect(frame, persons=raw_persons)
                    last_gestures = gestures
                else:
                    gestures = last_gestures

                frame_idx += 1

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
                self.uart_bridge.send_command(steering_cmd.value)

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
                target_str = f"#{self.target_manager.locked_target_id}" if self.target_manager.locked_target_id else "None"
                term_msg = (
                    f"\r[{self.state_machine.state.value}] Target: {target_str} | "
                    f"Cmd: [{steering_cmd.value}] | Tracks: {len(tracks)} | "
                    f"Latency: {t_latency:5.1f} ms | FPS: {avg_fps:4.1f}"
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
        "--conf", type=float, default=0.50,
        help="Person detection confidence threshold"
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
        "--no-threaded-cam", action="store_true",
        help="Disable asynchronous threaded camera and use standard blocking VideoCapture"
    )
    parser.add_argument(
        "--loss-timeout", type=float, default=3.0,
        help="Timeout in seconds before target loss triggers NEXUS OFF"
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
        use_threaded_cam=not args.no_threaded_cam
    )

    save_target = Path(args.save) if args.save else None
    app.run(
        source=args.source,
        show=not args.no_view,
        save_path=save_target
    )


if __name__ == "__main__":
    main()
