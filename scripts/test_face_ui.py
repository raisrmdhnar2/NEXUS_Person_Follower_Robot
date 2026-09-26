#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Expressive Face UI Interactive Demo
================================================================
File: scripts/test_face_ui.py

Demonstrates:
- Fullscreen & Fullsize animated emoji face UI (docs/ui.md).
- Interactive state transitions (Neutral, Greeting, Active, Lost, Timeout, Error).
- Gaze steering direction tracking and speaking mouth animation.

Usage:
    python3 scripts/test_face_ui.py
    python3 scripts/test_face_ui.py --fullscreen
    python3 scripts/test_face_ui.py --width 1280 --height 720
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
import numpy as np

from raspberry_pi.ui.face_display import DisplayMode, FaceDisplayManager, FaceExpression


def run_face_demo(fullscreen: bool = False, width: int = 1024, height: int = 600):
    print("=" * 65)
    print("NEXUS EXPRESSIVE FACE UI — INTERACTIVE DEMO")
    print("=" * 65)
    print("Keyboard Shortcuts:")
    print("  [1] IDLE / Neutral      [2] GREETING (Talking)")
    print("  [3] ACTIVATION (Wink)   [4] FOLLOWING")
    print("  [5] SEARCHING (Lost)    [6] RELIEVED (Reacquired)")
    print("  [7] SAD (Timeout)       [8] GOODBYE (Deactivated)")
    print("  [9] ERROR (Alert)")
    print("  ------------------------------------------------")
    print("  [A] Gaze Left (-)       [S] Gaze Center (x)    [D] Gaze Right (+)")
    print("  [T] Toggle Speaking Mouth")
    print("  [F] TOGGLE FULLSCREEN (Fullsize)")
    print("  [V] Cycle View Mode (Face Only / PiP / HUD)")
    print("  [Q] or [ESC] Exit")
    print("=" * 65)

    display = FaceDisplayManager(
        window_name="NEXUS — Expressive Face UI",
        width=width,
        height=height,
        fullscreen=fullscreen,
        display_mode=DisplayMode.FACE_ONLY
    )

    current_expr = FaceExpression.IDLE
    is_speaking = False
    steering = "x"
    status_label = "STANDBY // READY"

    # Create dummy synthetic camera frame for PiP preview demo
    dummy_cam = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_cam[:] = (35, 30, 45)
    cv2.putText(dummy_cam, "LIVE CAMERA FEED (PiP)", (120, 240),
                cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 200), 2)

    try:
        while True:
            # Render and display
            key = display.show(
                expression=current_expr,
                status_label=status_label,
                is_speaking=is_speaking,
                steering_cmd=steering,
                camera_frame=dummy_cam
            )

            if key in [ord("q"), ord("Q"), 27]:
                print("\n[FaceDemo] Exiting demo.")
                break
            elif key == ord("1"):
                current_expr = FaceExpression.IDLE
                status_label = "STANDBY // WAITING FOR VISITOR"
            elif key == ord("2"):
                current_expr = FaceExpression.GREETING
                status_label = "GREETING VISITOR // JARVIS VOICE"
                is_speaking = True
            elif key == ord("3"):
                current_expr = FaceExpression.ACTIVATION
                status_label = "TARGET LOCKED // PASSWORD VERIFIED"
                is_speaking = True
            elif key == ord("4"):
                current_expr = FaceExpression.FOLLOWING
                status_label = "FOLLOWING TARGET // ACTIVE"
                is_speaking = False
            elif key == ord("5"):
                current_expr = FaceExpression.SEARCHING
                status_label = "TARGET LOST // SEARCHING..."
                is_speaking = True
            elif key == ord("6"):
                current_expr = FaceExpression.RELIEVED
                status_label = "TARGET REACQUIRED // WELCOME BACK"
                is_speaking = False
            elif key == ord("7"):
                current_expr = FaceExpression.SAD
                status_label = "TARGET TIMEOUT // NEXUS OFF"
                is_speaking = True
            elif key == ord("8"):
                current_expr = FaceExpression.GOODBYE
                status_label = "DEACTIVATION // SEE YOU LATER"
                is_speaking = True
            elif key == ord("9"):
                current_expr = FaceExpression.ERROR
                status_label = "CRITICAL ERROR // SYSTEM HALTED"
                is_speaking = False
            elif key in [ord("a"), ord("A")]:
                steering = "-"
                print("[Steer] Gaze LEFT (-)")
            elif key in [ord("s"), ord("S")]:
                steering = "x"
                print("[Steer] Gaze CENTER (x)")
            elif key in [ord("d"), ord("D")]:
                steering = "+"
                print("[Steer] Gaze RIGHT (+)")
            elif key in [ord("t"), ord("T")]:
                is_speaking = not is_speaking
                print(f"[Speech] Speaking Mouth: {'ACTIVE' if is_speaking else 'OFF'}")

    finally:
        display.close()


def main():
    parser = argparse.ArgumentParser(description="NEXUS Expressive Face UI Interactive Demo")
    parser.add_argument("--fullscreen", "-f", action="store_true", help="Launch directly in fullscreen mode")
    parser.add_argument("--width", type=int, default=1024, help="Window canvas width (default 1024)")
    parser.add_argument("--height", type=int, default=600, help="Window canvas height (default 600)")

    args = parser.parse_args()
    run_face_demo(fullscreen=args.fullscreen, width=args.width, height=args.height)


if __name__ == "__main__":
    main()
