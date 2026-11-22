#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Remote Top Module v2 (top_module_remote_v2.py)
============================================================================
File: top_module_remote_v2.py

Peningkatan di Versi 2:
    - Menghapus ketergantungan pada OpenCV TrackerMIL lokal yang lambat di CPU ARM (~4.2 detik).
    - Sepenuhnya berbasis IoU Tracking ultra-ringan (< 0.1 ms) + Asynchronous YOLO di NVIDIA A100 GPU.
    - Frame rate stabil di 30–60 FPS konstan baik saat Standby (OFF) maupun saat Mengikuti (ON).
    - Bebas dari thermal throttling dan bebas lag.

Penggunaan:
    QT_QPA_PLATFORM=xcb python top_module_remote_v2.py --server https://tjf578vg-8080.asse.devtunnels.ms/ --display-mode face_only
    QT_QPA_PLATFORM=xcb python top_module_remote_v2.py --server https://tjf578vg-8080.asse.devtunnels.ms/ --display-mode camera_hud
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

# Import NEXUS modules
from raspberry_pi.vision.remote_person_detector import AsyncRemotePersonDetector
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
from raspberry_pi.ui.speech_manager import SpeechManager, VoiceEvent
from raspberry_pi.ui.greeting_manager import GreetingManager
from raspberry_pi.ui.face_display import FaceDisplayManager, DisplayMode, FaceExpression
from top_module import NexusState, NexusStateMachine, draw_top_module_hud


class TopModuleRemoteV2:
    """
    Client-side Coordinator V2 untuk Raspberry Pi 4 dengan Remote GPU Inference.
    Menggunakan IoU Tracker murni untuk kecepatan maksimal tanpa bottleneck TrackerMIL.
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8000",
        flip_horizontal: bool = True,
        target_loss_timeout: float = 3.0,
        serial_port: Optional[str] = "auto",
        baudrate: int = 115200,
        no_uart: bool = False,
        deadzone: float = 0.15,
        gesture_interval: int = 4,
        no_speech: bool = False,
        greeting_cooldown: float = 15.0,
        greeting_empty_reset: float = 5.0,
        use_threaded_cam: bool = True,
        use_mjpeg: bool = False,
        face_fullscreen: bool = False,
        display_mode: str = "face_only"
    ):
        print("=" * 65)
        print("NEXUS PERSON FOLLOWER — REMOTE CLIENT V2 INITIALIZATION")
        print("=" * 65)
        print(f"[RemoteClientV2] Connecting to GPU Server: {server_url}")

        # 1. State Machine
        self.state_machine = NexusStateMachine(toggle_cooldown=3.0)

        # 2. Async Remote Person Detector (Background worker ke NVIDIA A100 GPU)
        self.person_detector = AsyncRemotePersonDetector(
            server_url=server_url,
            target_size=(320, 240),
            jpeg_quality=70,
            timeout=2.5,
            min_interval=0.15
        )
        is_alive, msg = self.person_detector.check_health()
        if is_alive:
            print(f"[RemoteClientV2] ✅ GPU Server Connected: {msg}")
        else:
            print(f"[RemoteClientV2] ⚠️ Warning: Gagal menghubungi server saat inisialisasi ({msg}).")
            print("                  Akan terus mencoba menyambung saat kamera berjalan.")

        self.use_mjpeg = use_mjpeg

        # 3. Multi-Person IoU Tracker (Ultra-cepat ~0.05 ms di RPi)
        self.tracker = PersonTracker(max_missed_frames=150, iou_threshold=0.25)

        # 4. Target Lock Manager
        self.target_manager = TargetLockManager(loss_timeout_seconds=target_loss_timeout)

        # 5. Follow Controller
        self.follow_controller = FollowController(deadzone=deadzone)

        # 6. ESP32 UART Bridge
        self.uart_bridge = Esp32UartBridge(
            port=serial_port,
            baudrate=baudrate,
            enabled=not no_uart
        )
        print(f"[RemoteClientV2] UART Bridge: {self.uart_bridge.status_label}")

        # 6.5 Audio & Speech Manager
        self.speech_manager = SpeechManager(enabled=not no_speech)

        # 6.6 Greeting Manager
        self.greeting_manager = GreetingManager(
            cooldown_seconds=greeting_cooldown,
            empty_reset_seconds=greeting_empty_reset
        )
        self._greeting_finished_flag = False

        # 6.7 Expressive Face Display
        disp_enum = DisplayMode.FACE_ONLY
        try:
            disp_enum = DisplayMode(display_mode.lower())
        except Exception:
            pass

        self.face_display = FaceDisplayManager(
            window_name="NEXUS — Remote Mode v2",
            width=1024,
            height=600,
            fullscreen=face_fullscreen,
            display_mode=disp_enum
        )

        # 7. Gesture Recognizer
        self.gesture_recognizer = GestureRecognizer()

        # Configs
        self.flip_horizontal = flip_horizontal
        self.gesture_interval = max(1, gesture_interval)
        self.use_threaded_cam = use_threaded_cam

        self._last_deactivate_time: float = 0.0
        self._last_reacquire_time: float = 0.0
        self.last_following_checkin: float = 0.0
        self.following_checkin_interval: float = 20.0

    def _on_greeting_complete(self) -> None:
        self._greeting_finished_flag = True

    def _determine_face_expression(self, target_event: TargetEvent) -> Tuple[FaceExpression, str]:
        now = time.time()
        if target_event == TargetEvent.TARGET_REACQUIRED or (now - self._last_reacquire_time) < 1.5:
            return FaceExpression.RELIEVED, "TARGET REACQUIRED // WELCOME BACK"

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
            if (now - self._last_deactivate_time) < 2.0 or self.greeting_manager.require_scene_clear:
                return FaceExpression.GOODBYE, "DEACTIVATED // SEE YOU LATER"
            return FaceExpression.IDLE, "STANDBY // READY FOR VISITOR"

    def run(
        self,
        source: int = 0,
        output_path: Optional[str] = None,
        max_frames: Optional[int] = None,
        show: bool = True
    ) -> None:
        print(f"\n[RemoteClientV2] Starting video acquisition from source: {source}...")

        is_camera = str(source).isdigit()
        src_id = int(source) if is_camera else source

        if is_camera and self.use_threaded_cam:
            codec_str = "MJPG" if self.use_mjpeg else "YUYV"
            print(f"[RemoteClientV2] Initializing High-Speed Threaded Camera on source '{source}' ({codec_str} 640x480 @ 30 FPS)...")
            cap = ThreadedCamera(
                source=src_id,
                width=640,
                height=480,
                fps=30,
                use_mjpeg=self.use_mjpeg
            ).start()
        else:
            print(f"[RemoteClientV2] Opening standard video source: {source}...")
            cap = cv2.VideoCapture(src_id)
            if self.use_mjpeg:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        is_opened = cap.is_opened() if hasattr(cap, "is_opened") else cap.isOpened()
        if not is_opened:
            print(f"[ERROR] Could not open video source '{source}'.")
            return

        frame_idx = 0
        fps_buffer: List[float] = []
        last_gestures: List = []

        try:
            while (cap.is_opened() if hasattr(cap, "is_opened") else cap.isOpened()):
                if max_frames and frame_idx >= max_frames:
                    break

                t_start = time.perf_counter()

                if self.use_threaded_cam and hasattr(cap, "read"):
                    try:
                        grabbed, frame = cap.read(wait_new=True, timeout=0.04)
                    except TypeError:
                        grabbed, frame = cap.read()
                else:
                    grabbed, frame = cap.read()

                if not grabbed or frame is None:
                    time.sleep(0.01)
                    continue

                if self.flip_horizontal:
                    frame = cv2.flip(frame, 1)

                frame_h, frame_w = frame.shape[:2]
                target_event = TargetEvent.NONE

                if self._greeting_finished_flag:
                    self._greeting_finished_flag = False
                    self.state_machine.finish_greeting()

                # Step 1: Deteksi Orang Non-Blocking dari Server GPU A100
                raw_persons = self.person_detector.detect(frame)
                tracks = self.tracker.update(raw_persons)

                # Step 2: State Machine & Tracking Pipeline
                if self.state_machine.state == NexusState.ON:
                    # Target Terkunci: Update via IoU Tracker murni (< 0.1 ms!)
                    locked_person, target_event = self.target_manager.update(tracks)

                    if target_event == TargetEvent.TARGET_REACQUIRED:
                        self._last_reacquire_time = time.time()
                        self.speech_manager.stop()
                        self.speech_manager.speak_target_locked()
                    elif target_event == TargetEvent.TARGET_LOST:
                        self.speech_manager.speak_target_lost()
                    elif target_event == TargetEvent.TARGET_LOST_TIMEOUT:
                        self.target_manager.unlock_target()
                        self.greeting_manager.on_deactivation()
                        self._last_deactivate_time = time.time()
                        self.speech_manager.speak_target_timeout()
                        self.state_machine.force_off("Target Lost Timeout")

                    # Suara Check-in berkala
                    now_t = time.time()
                    if self.target_manager.is_target_present and (now_t - self.last_following_checkin) >= self.following_checkin_interval:
                        self.last_following_checkin = now_t
                        self.speech_manager.speak_following()

                    # Gestur Deaktivasi (Peace Sign) dari ROI target
                    if frame_idx % self.gesture_interval == 0:
                        if self.target_manager.is_target_present and self.target_manager.locked_person:
                            gestures = self.gesture_recognizer.detect_roi(
                                frame, self.target_manager.locked_person.bbox
                            )
                        else:
                            gestures = []
                        last_gestures = gestures
                    else:
                        gestures = last_gestures

                    if self.gesture_recognizer.check_password_event(gestures):
                        pwd_gesture = next((g for g in gestures if (getattr(g, "is_victory", False) or g.is_open_palm)), None)
                        if pwd_gesture is not None and not self.state_machine.is_in_cooldown:
                            self.target_manager.unlock_target()
                            self.greeting_manager.on_deactivation()
                            self._last_deactivate_time = time.time()
                            self.speech_manager.speak_deactivation()
                            self.state_machine.handle_password_gesture(reason="Deactivation Password Accepted")

                else:
                    # NEXUS OFF / GREETING
                    if frame_idx % self.gesture_interval == 0:
                        gestures = self.gesture_recognizer.detect(frame, persons=raw_persons)
                        last_gestures = gestures
                    else:
                        gestures = last_gestures

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

                    # Password Aktivasi (Peace Sign)
                    if self.gesture_recognizer.check_password_event(gestures):
                        pwd_gesture = next((g for g in gestures if (getattr(g, "is_victory", False) or g.is_open_palm)), None)
                        if not self.state_machine.is_in_cooldown:
                            cand = None
                            if pwd_gesture and tracks:
                                cand = self.target_manager.associate_gesture_with_person(tracks, pwd_gesture)
                            elif tracks:
                                cand = tracks[0]

                            if cand is not None:
                                self.greeting_manager.finish_greeting()
                                self.greeting_manager.mark_interacted(cand.track_id)
                                self.target_manager.lock_target(cand.track_id, cand)
                                self.state_machine.handle_password_gesture(reason=f"Target #{cand.track_id} Locked")
                                self.speech_manager.speak_activation()
                                self.last_following_checkin = time.time()

                frame_idx += 1

                # Step 3: Follow Control & ESP32 UART
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

                # Step 4: Telemetry & Benchmark
                t_latency = (time.perf_counter() - t_start) * 1000.0
                fps_val = 1000.0 / t_latency if t_latency > 0 else 0.0
                fps_buffer.append(fps_val)
                if len(fps_buffer) > 30:
                    fps_buffer.pop(0)
                avg_fps = sum(fps_buffer) / len(fps_buffer)

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

                state_str = "ON" if self.state_machine.state == NexusState.ON else "OFF"
                target_str = f"#{self.target_manager.locked_target_id}" if self.target_manager.locked_target_id else "None"
                rtt_str = f"{self.person_detector.last_rtt_ms:4.1f}ms" if self.person_detector.last_rtt_ms > 0 else "Local"
                term_msg = (
                    f"\r[RemoteV2 {state_str}] Target: {target_str} | "
                    f"UART: '{self.uart_bridge.last_command}' | "
                    f"FPS: {avg_fps:4.1f} | Latency: {t_latency:4.1f}ms | RTT: {rtt_str} "
                )
                sys.stdout.write(term_msg)
                sys.stdout.flush()

                if show:
                    expr, face_status = self._determine_face_expression(target_event)
                    key = self.face_display.show(
                        expression=expr,
                        status_label=face_status,
                        is_speaking=self.speech_manager.is_speaking,
                        steering_cmd=steering_cmd.value,
                        camera_frame=annotated_frame
                    )
                    if key in [ord("q"), 27]:
                        print("\n[RemoteClientV2] Termination requested.")
                        break
                    elif key in [ord("m"), ord("M")]:
                        self.flip_horizontal = not self.flip_horizontal
                    elif key in [ord("t"), ord("T"), ord("p"), ord("P")]:
                        if self.state_machine.state in [NexusState.OFF, NexusState.GREETING]:
                            if tracks:
                                self.speech_manager.stop()
                                self.greeting_manager.finish_greeting()
                                self.greeting_manager.mark_interacted(tracks[0].track_id)
                                self.target_manager.lock_target(tracks[0].track_id, tracks[0])
                            self.speech_manager.speak_activation()
                            self.last_following_checkin = time.time()
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")
                        else:
                            self.target_manager.unlock_target()
                            self.greeting_manager.on_deactivation()
                            self._last_deactivate_time = time.time()
                            self.speech_manager.speak_deactivation()
                            self.state_machine.handle_password_gesture(reason="Manual Key Toggle")

        except KeyboardInterrupt:
            print("\n[RemoteClientV2] Interrupted by user.")
        finally:
            if hasattr(self, "person_detector") and hasattr(self.person_detector, "stop"):
                self.person_detector.stop()
            if hasattr(self, "face_display"):
                self.face_display.close()
            if hasattr(self, "speech_manager"):
                self.speech_manager.stop()
            if self.use_threaded_cam:
                cap.stop()
            else:
                cap.release()
            print("\n[RemoteClientV2] Cleanup finished. Exiting.")


def main():
    parser = argparse.ArgumentParser(description="NEXUS Remote Person Follower Robot V2")
    parser.add_argument("--server", type=str, default="http://127.0.0.1:8000", help="URL Server GPU (e.g. https://xxxx.devtunnels.ms)")
    parser.add_argument("--source", type=int, default=0, help="Camera video source (default: 0)")
    parser.add_argument("--port", type=str, default="auto", help="ESP32 serial port (default: auto)")
    parser.add_argument("--baudrate", type=int, default=115200, help="ESP32 serial baudrate")
    parser.add_argument("--no-uart", action="store_true", help="Run without ESP32 UART serial connection")
    parser.add_argument("--no-speech", action="store_true", help="Disable JARVIS audio voice feedback")
    parser.add_argument("--display-mode", type=str, default="face_only", choices=["face_only", "camera_hud", "side_by_side", "pip", "none"])
    parser.add_argument("--face-fullscreen", action="store_true", help="Open UI display in fullscreen")
    parser.add_argument("--no-threaded-cam", action="store_true", help="Disable threaded camera capture")
    parser.add_argument("--mjpeg", action="store_true", help="Use hardware MJPEG stream from webcam")
    args = parser.parse_args()

    client = TopModuleRemoteV2(
        server_url=args.server,
        serial_port=args.port,
        baudrate=args.baudrate,
        no_uart=args.no_uart,
        no_speech=args.no_speech,
        display_mode=args.display_mode,
        face_fullscreen=args.face_fullscreen,
        use_threaded_cam=not args.no_threaded_cam,
        use_mjpeg=args.mjpeg
    )
    client.run(source=args.source)


if __name__ == "__main__":
    main()
