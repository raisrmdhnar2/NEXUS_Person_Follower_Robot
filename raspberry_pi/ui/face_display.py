#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Expressive Face UI & Screen Manager
================================================================
File: raspberry_pi/ui/face_display.py

Implements:
1. Expressive animated emoji face renderer (Procedural Vector Graphics + Video Loop support).
2. Screen UI State Machine aligned with `docs/ui.md` & `state_machine.md`.
3. Support for Fullsize / Fullscreen display (`cv2.WINDOW_FULLSCREEN`).
4. Display modes:
   - FACE_ONLY: Clean expressive robot face for the robot's physical display.
   - FACE_PIP: Robot face with Picture-in-Picture live camera preview.
   - CAMERA_HUD: Developer debug camera view with bounding boxes and telemetry.
"""

import enum
import math
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np


class DisplayMode(enum.Enum):
    """View modes for the screen interface."""
    FACE_ONLY = "face_only"      # Fullsize clean robot face (emoji)
    FACE_PIP = "face_pip"        # Robot face with camera Picture-in-Picture
    CAMERA_HUD = "camera_hud"    # Original developer debug HUD


class FaceExpression(enum.Enum):
    """UI Face States corresponding to docs/ui.md."""
    IDLE = "idle"                # Standby / Neutral / Calm
    GREETING = "greeting"        # Happy talking mouth / Welcoming
    ACTIVATION = "activation"    # Excited / Target Locked / Wink
    FOLLOWING = "following"      # Focused friendly / Gaze tracking
    SEARCHING = "searching"      # Confused / Looking around (Target Lost)
    RELIEVED = "relieved"        # Cheerful smile (Target Reacquired)
    SAD = "sad"                  # Disappointed / Downturned (Loss Timeout)
    GOODBYE = "goodbye"          # Polite wave smile (Deactivation)
    ERROR = "error"              # Dizzy / Warning (System Error)


class FaceDisplayManager:
    """
    Manages the Robot Face Display on screen, supporting real-time
    procedural animation, video playback, and fullscreen mode.
    """

    # Color Palette (BGR)
    COLOR_BG = (12, 10, 15)              # Deep Dark Violet / Black
    COLOR_CYAN = (255, 220, 0)           # Bright Cyan Neon
    COLOR_GREEN = (100, 240, 50)         # Emerald Green Neon
    COLOR_AMBER = (0, 180, 255)          # Amber / Orange Neon
    COLOR_LAVENDER = (220, 160, 180)     # Soft Lavender
    COLOR_RED = (50, 50, 255)            # Bright Alert Red
    COLOR_WHITE = (245, 245, 245)        # Crisp White
    COLOR_DARK_BORDER = (45, 40, 55)     # Subdued border

    def __init__(
        self,
        window_name: str = "NEXUS — Expressive Face UI",
        width: int = 1024,
        height: int = 600,
        fullscreen: bool = False,
        display_mode: DisplayMode = DisplayMode.FACE_ONLY,
        assets_dir: Optional[Path] = None
    ):
        """
        Args:
            window_name: Title of the OpenCV GUI window.
            width: Default window canvas width in pixels.
            height: Default window canvas height in pixels.
            fullscreen: Whether to launch directly in fullscreen mode.
            display_mode: Initial view mode (FACE_ONLY, FACE_PIP, CAMERA_HUD).
            assets_dir: Path to directory containing video face clips (optional).
        """
        self.window_name = window_name
        self.width = width
        self.height = height
        self.is_fullscreen = fullscreen
        self.display_mode = display_mode
        self.is_window_created = False

        # Asset Directory for optional pre-rendered video clips (docs/ui.md)
        if assets_dir is None:
            self.assets_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "ui" / "face"
        else:
            self.assets_dir = Path(assets_dir)

        # Video Capture cache for video loop mode
        self.video_captures: Dict[FaceExpression, cv2.VideoCapture] = {}
        self.current_video_expr: Optional[FaceExpression] = None
        self._init_video_assets()

        # Animation Timing States
        self.start_time = time.time()
        self.last_blink_time = time.time()
        self.blink_interval = 3.5          # Seconds between natural blinks
        self.blink_duration = 0.18         # Duration of blink
        self.is_blinking = False

        # Smooth Gaze Tracking (-1.0 = left, 0.0 = center, 1.0 = right)
        self.current_gaze_x = 0.0
        self.target_gaze_x = 0.0

        # Current Active Expression
        self.current_expression = FaceExpression.IDLE

    def _init_video_assets(self):
        """Scans assets directory for optional pre-rendered MP4 video clips."""
        if not self.assets_dir.exists():
            return

        file_map = {
            FaceExpression.IDLE: "face_neutral.mp4",
            FaceExpression.GREETING: "face_greeting.mp4",
            FaceExpression.ACTIVATION: "face_excited.mp4",
            FaceExpression.FOLLOWING: "face_follow_center.mp4",
            FaceExpression.SEARCHING: "face_searching.mp4",
            FaceExpression.RELIEVED: "face_reacquired.mp4",
            FaceExpression.SAD: "face_timeout.mp4",
            FaceExpression.GOODBYE: "face_goodbye.mp4",
            FaceExpression.ERROR: "face_error.mp4",
        }

        for expr, fname in file_map.items():
            fpath = self.assets_dir / fname
            if fpath.exists():
                cap = cv2.VideoCapture(str(fpath))
                if cap.isOpened():
                    self.video_captures[expr] = cap

    def setup_window(self):
        """Creates and configures the OpenCV window with fullscreen capability."""
        if self.is_window_created:
            return

        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        if self.is_fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.resizeWindow(self.window_name, self.width, self.height)

        self.is_window_created = True

    def toggle_fullscreen(self):
        """Toggles fullscreen state on and off."""
        self.is_fullscreen = not self.is_fullscreen
        self.setup_window()
        if self.is_fullscreen:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        else:
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, self.width, self.height)
        print(f"[FaceDisplay] Fullscreen: {'ENABLED' if self.is_fullscreen else 'WINDOWED'}")

    def cycle_display_mode(self) -> DisplayMode:
        """Cycles between FACE_ONLY, FACE_PIP, and CAMERA_HUD view modes."""
        modes = [DisplayMode.FACE_ONLY, DisplayMode.FACE_PIP, DisplayMode.CAMERA_HUD]
        cur_idx = modes.index(self.display_mode)
        self.display_mode = modes[(cur_idx + 1) % len(modes)]
        print(f"[FaceDisplay] View Mode switched to: {self.display_mode.value.upper()}")
        return self.display_mode

    # -------------------------------------------------------------------------
    # Procedural Vector Animation Rendering
    # -------------------------------------------------------------------------
    def _update_animation_clocks(self):
        """Updates internal micro-blinking and timing parameters."""
        now = time.time()
        elapsed_since_blink = now - self.last_blink_time

        if not self.is_blinking:
            if elapsed_since_blink >= self.blink_interval:
                self.is_blinking = True
                self.last_blink_time = now
        else:
            if now - self.last_blink_time >= self.blink_duration:
                self.is_blinking = False
                self.last_blink_time = now

        # Smooth gaze transition (lerp)
        self.current_gaze_x += (self.target_gaze_x - self.current_gaze_x) * 0.25

    def _render_procedural_face(
        self,
        canvas: np.ndarray,
        expression: FaceExpression,
        is_speaking: bool,
        steering_cmd: str,
        status_label: str
    ):
        """
        Renders a glowing cybernetic emoji face on the canvas with smooth animation.
        """
        h, w = canvas.shape[:2]
        now = time.time()

        # Update gaze based on steering command ('-', 'x', '+')
        if steering_cmd == "-":
            self.target_gaze_x = -0.75   # Look Left
        elif steering_cmd == "+":
            self.target_gaze_x = 0.75    # Look Right
        else:
            self.target_gaze_x = 0.0     # Look Center

        self._update_animation_clocks()

        # Eye Geometry
        center_y = int(h * 0.44)
        eye_spacing = int(w * 0.22)
        left_eye_center = (int(w / 2 - eye_spacing), center_y)
        right_eye_center = (int(w / 2 + eye_spacing), center_y)
        eye_rx = int(w * 0.085)
        eye_ry = int(h * 0.17)

        # Base Color based on Expression
        if expression in [FaceExpression.ACTIVATION, FaceExpression.FOLLOWING, FaceExpression.RELIEVED]:
            primary_color = self.COLOR_GREEN
        elif expression == FaceExpression.SEARCHING:
            primary_color = self.COLOR_AMBER
        elif expression == FaceExpression.ERROR:
            # Alternating pulse red / yellow
            primary_color = self.COLOR_RED if int(now * 4) % 2 == 0 else self.COLOR_AMBER
        elif expression == FaceExpression.SAD:
            primary_color = self.COLOR_LAVENDER
        else:
            primary_color = self.COLOR_CYAN

        # Glow Layer (Soft outer circle)
        glow_radius = int(eye_rx * 1.35)
        glow_color = tuple(int(c * 0.28) for c in primary_color)
        cv2.circle(canvas, left_eye_center, glow_radius, glow_color, -1, cv2.LINE_AA)
        cv2.circle(canvas, right_eye_center, glow_radius, glow_color, -1, cv2.LINE_AA)

        # Draw Eyes according to Expression
        if self.is_blinking and expression not in [FaceExpression.ERROR, FaceExpression.GREETING, FaceExpression.ACTIVATION]:
            # Blinking Slit
            cv2.line(canvas, (left_eye_center[0] - eye_rx, center_y),
                     (left_eye_center[0] + eye_rx, center_y), primary_color, 8, cv2.LINE_AA)
            cv2.line(canvas, (right_eye_center[0] - eye_rx, center_y),
                     (right_eye_center[0] + eye_rx, center_y), primary_color, 8, cv2.LINE_AA)

        elif expression in [FaceExpression.GREETING, FaceExpression.ACTIVATION, FaceExpression.RELIEVED]:
            # Happy Curving Eyes (^_^ / ^o^)
            arc_thickness = 14 if expression == FaceExpression.ACTIVATION else 11
            cv2.ellipse(canvas, left_eye_center, (eye_rx, eye_ry), 0, 195, 345, primary_color, arc_thickness, cv2.LINE_AA)
            cv2.ellipse(canvas, right_eye_center, (eye_rx, eye_ry), 0, 195, 345, primary_color, arc_thickness, cv2.LINE_AA)

            # Sparkle in eyes for Activation / Relieved
            if expression in [FaceExpression.ACTIVATION, FaceExpression.RELIEVED]:
                sparkle_pulse = int(5 + math.sin(now * 10) * 3)
                cv2.circle(canvas, (left_eye_center[0], center_y - 15), sparkle_pulse, self.COLOR_WHITE, -1, cv2.LINE_AA)
                cv2.circle(canvas, (right_eye_center[0], center_y - 15), sparkle_pulse, self.COLOR_WHITE, -1, cv2.LINE_AA)

        elif expression == FaceExpression.SEARCHING:
            # Confused Eyes: Left eye slightly wider, looking around
            gaze_shift_x = int(math.sin(now * 3.5) * (eye_rx * 0.55))
            cv2.ellipse(canvas, left_eye_center, (eye_rx + 6, eye_ry + 6), 0, 0, 360, primary_color, 8, cv2.LINE_AA)
            cv2.ellipse(canvas, right_eye_center, (eye_rx - 4, eye_ry - 4), 0, 0, 360, primary_color, 8, cv2.LINE_AA)
            # Pupils searching
            p_rad = int(eye_rx * 0.42)
            cv2.circle(canvas, (left_eye_center[0] + gaze_shift_x, center_y), p_rad, primary_color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (right_eye_center[0] + gaze_shift_x, center_y), p_rad, primary_color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (left_eye_center[0] + gaze_shift_x - 4, center_y - 5), 4, self.COLOR_WHITE, -1, cv2.LINE_AA)
            cv2.circle(canvas, (right_eye_center[0] + gaze_shift_x - 4, center_y - 5), 4, self.COLOR_WHITE, -1, cv2.LINE_AA)

        elif expression == FaceExpression.SAD:
            # Sad / Disappointed Downturned Eyelids (v_v)
            cv2.ellipse(canvas, left_eye_center, (eye_rx, eye_ry), 0, 15, 165, primary_color, 9, cv2.LINE_AA)
            cv2.ellipse(canvas, right_eye_center, (eye_rx, eye_ry), 0, 15, 165, primary_color, 9, cv2.LINE_AA)

        elif expression == FaceExpression.ERROR:
            # Dizzy / Cross Eyes (X_X)
            cross_r = int(eye_rx * 0.75)
            for center in [left_eye_center, right_eye_center]:
                cv2.line(canvas, (center[0] - cross_r, center_y - cross_r),
                         (center[0] + cross_r, center_y + cross_r), primary_color, 10, cv2.LINE_AA)
                cv2.line(canvas, (center[0] + cross_r, center_y - cross_r),
                         (center[0] - cross_r, center_y + cross_r), primary_color, 10, cv2.LINE_AA)

        else:
            # IDLE / FOLLOWING / GOODBYE: Focused Capsule Eyes with Gaze Tracking
            gaze_offset_x = int(self.current_gaze_x * (eye_rx * 0.50))
            # Outer Ring
            cv2.ellipse(canvas, left_eye_center, (eye_rx, eye_ry), 0, 0, 360, primary_color, 9, cv2.LINE_AA)
            cv2.ellipse(canvas, right_eye_center, (eye_rx, eye_ry), 0, 0, 360, primary_color, 9, cv2.LINE_AA)

            # Pupil with highlight
            pupil_r = int(eye_rx * 0.44)
            p_left = (left_eye_center[0] + gaze_offset_x, center_y)
            p_right = (right_eye_center[0] + gaze_offset_x, center_y)
            cv2.circle(canvas, p_left, pupil_r, primary_color, -1, cv2.LINE_AA)
            cv2.circle(canvas, p_right, pupil_r, primary_color, -1, cv2.LINE_AA)
            cv2.circle(canvas, (p_left[0] - 5, center_y - 6), 5, self.COLOR_WHITE, -1, cv2.LINE_AA)
            cv2.circle(canvas, (p_right[0] - 5, center_y - 6), 5, self.COLOR_WHITE, -1, cv2.LINE_AA)

        # ---------------------------------------------------------------------
        # Mouth Rendering
        # ---------------------------------------------------------------------
        mouth_y = int(h * 0.72)
        mouth_center = (int(w / 2), mouth_y)
        mouth_w = int(w * 0.16)

        if is_speaking:
            # Talking Mouth (rhythmic sinusoidal opening)
            speech_open = int(abs(math.sin(now * 11)) * (h * 0.055)) + 4
            cv2.ellipse(canvas, mouth_center, (mouth_w, max(6, speech_open)), 0, 0, 360, primary_color, -1, cv2.LINE_AA)
            cv2.ellipse(canvas, mouth_center, (mouth_w, max(6, speech_open)), 0, 0, 360, self.COLOR_WHITE, 3, cv2.LINE_AA)

        elif expression in [FaceExpression.ACTIVATION, FaceExpression.GREETING, FaceExpression.RELIEVED]:
            # Big Cheerful Smile
            smile_depth = int(h * 0.055)
            cv2.ellipse(canvas, mouth_center, (mouth_w, smile_depth), 0, 0, 180, primary_color, 8, cv2.LINE_AA)

        elif expression == FaceExpression.FOLLOWING:
            # Subtle Friendly Smile
            cv2.ellipse(canvas, mouth_center, (int(mouth_w * 0.8), int(h * 0.035)), 0, 0, 180, primary_color, 6, cv2.LINE_AA)

        elif expression == FaceExpression.SEARCHING:
            # 'o' Shaped Worried Mouth
            cv2.circle(canvas, mouth_center, int(w * 0.035), primary_color, 6, cv2.LINE_AA)

        elif expression == FaceExpression.SAD:
            # Downturned Mouth
            cv2.ellipse(canvas, (mouth_center[0], mouth_y + 15), (mouth_w, int(h * 0.04)), 0, 180, 360, primary_color, 7, cv2.LINE_AA)

        elif expression == FaceExpression.ERROR:
            # Zigzag / Shock Mouth
            zw = int(mouth_w * 0.7)
            points = np.array([
                [mouth_center[0] - zw, mouth_y],
                [mouth_center[0] - zw // 2, mouth_y - 12],
                [mouth_center[0], mouth_y + 12],
                [mouth_center[0] + zw // 2, mouth_y - 12],
                [mouth_center[0] + zw, mouth_y]
            ], np.int32)
            cv2.polylines(canvas, [points], False, primary_color, 6, cv2.LINE_AA)

        else:
            # IDLE: Calm Horizontal Mouth Line
            cv2.line(canvas, (mouth_center[0] - int(mouth_w * 0.6), mouth_y),
                     (mouth_center[0] + int(mouth_w * 0.6), mouth_y), primary_color, 5, cv2.LINE_AA)

        # ---------------------------------------------------------------------
        # Top Futuristic Status Pill
        # ---------------------------------------------------------------------
        pill_text = f"NEXUS // {status_label}"
        (tw, th), bl = cv2.getTextSize(pill_text, cv2.FONT_HERSHEY_DUPLEX, 0.65, 1)
        pw = tw + 40
        ph = th + 18
        px1 = (w - pw) // 2
        py1 = 18
        cv2.rectangle(canvas, (px1, py1), (px1 + pw, py1 + ph), (25, 20, 35), -1)
        cv2.rectangle(canvas, (px1, py1), (px1 + pw, py1 + ph), primary_color, 1, cv2.LINE_AA)
        cv2.putText(canvas, pill_text, (px1 + 20, py1 + ph - bl - 3),
                    cv2.FONT_HERSHEY_DUPLEX, 0.65, primary_color, 1, cv2.LINE_AA)

        # Bottom Subtitle Hint
        hint_text = "[F] Fullscreen | [V] Switch View Mode | [Q] Exit"
        (hw, hh), _ = cv2.getTextSize(hint_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.putText(canvas, hint_text, ((w - hw) // 2, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 110, 140), 1, cv2.LINE_AA)

    # -------------------------------------------------------------------------
    # Composite Master Frame Builder
    # -------------------------------------------------------------------------
    def build_frame(
        self,
        expression: FaceExpression,
        status_label: str,
        is_speaking: bool = False,
        steering_cmd: str = "x",
        camera_frame: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Builds the visual frame based on current display_mode.

        Returns:
            Rendered BGR image ready for display.
        """
        self.current_expression = expression

        # Mode 1: CAMERA_HUD
        if self.display_mode == DisplayMode.CAMERA_HUD and camera_frame is not None:
            return camera_frame

        # Prepare Face Canvas
        face_canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        face_canvas[:] = self.COLOR_BG

        # Try Video Clip playback first (if video file exists for expression)
        video_rendered = False
        if expression in self.video_captures:
            cap = self.video_captures[expression]
            ret, vframe = cap.read()
            if not ret or vframe is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, vframe = cap.read()
            if ret and vframe is not None:
                face_canvas = cv2.resize(vframe, (self.width, self.height))
                video_rendered = True

        # Fallback to Procedural Vector Animation
        if not video_rendered:
            self._render_procedural_face(
                canvas=face_canvas,
                expression=expression,
                is_speaking=is_speaking,
                steering_cmd=steering_cmd,
                status_label=status_label
            )

        # Mode 2: FACE_PIP (Embed camera stream in bottom-right corner)
        if self.display_mode == DisplayMode.FACE_PIP and camera_frame is not None:
            pip_w = int(self.width * 0.26)
            pip_h = int(self.height * 0.28)
            pip_x = self.width - pip_w - 20
            pip_y = self.height - pip_h - 40

            resized_cam = cv2.resize(camera_frame, (pip_w, pip_h))
            cv2.rectangle(face_canvas, (pip_x - 3, pip_y - 3),
                          (pip_x + pip_w + 3, pip_y + pip_h + 3), self.COLOR_CYAN, 2)
            face_canvas[pip_y:pip_y + pip_h, pip_x:pip_x + pip_w] = resized_cam

            # PiP Badge
            cv2.putText(face_canvas, "CAM PREVIEW", (pip_x + 8, pip_y + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, self.COLOR_CYAN, 1, cv2.LINE_AA)

        return face_canvas

    def show(
        self,
        expression: FaceExpression,
        status_label: str,
        is_speaking: bool = False,
        steering_cmd: str = "x",
        camera_frame: Optional[np.ndarray] = None
    ) -> int:
        """
        Renders and displays the frame to the OpenCV window.

        Returns:
            Key code pressed by user (from cv2.waitKey(1) & 0xFF).
        """
        self.setup_window()
        frame = self.build_frame(
            expression=expression,
            status_label=status_label,
            is_speaking=is_speaking,
            steering_cmd=steering_cmd,
            camera_frame=camera_frame
        )
        cv2.imshow(self.window_name, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in [ord("f"), ord("F")]:
            self.toggle_fullscreen()
        elif key in [ord("v"), ord("V")]:
            self.cycle_display_mode()

        return key

    def close(self):
        """Releases video assets and cleans up GUI."""
        for cap in self.video_captures.values():
            cap.release()
        self.video_captures.clear()
        if self.is_window_created:
            try:
                cv2.destroyWindow(self.window_name)
            except Exception:
                pass
            self.is_window_created = False
