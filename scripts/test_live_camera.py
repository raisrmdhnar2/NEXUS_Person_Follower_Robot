#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Live Camera Test & Latency / FPS Benchmark
=========================================================================
File: scripts/test_live_camera.py

Responsibility:
    Tests the live camera feed (USB webcam or CSI camera), monitors frame acquisition,
    and measures real-time capture latency (ms) and framerate (FPS).
    Supports both the NEXUS zero-latency ThreadedCamera (native YUYV) and standard
    OpenCV VideoCapture for direct performance comparison.

Usage Examples:
    # 1. Run with default ThreadedCamera (YUYV 640x480 @ 30 FPS)
    python3 scripts/test_live_camera.py

    # 2. Test standard blocking OpenCV VideoCapture for comparison
    python3 scripts/test_live_camera.py --standard

    # 3. Specify custom camera index or resolution
    python3 scripts/test_live_camera.py --source 0 --width 640 --height 480 --fps 30

    # 4. Run headless (terminal-only output, no GUI window)
    python3 scripts/test_live_camera.py --no-view

    # 5. Test with MJPEG compression
    python3 scripts/test_live_camera.py --mjpeg

Keyboard Controls:
    'q' / ESC : Exit test and print summary report
    'm'       : Toggle horizontal mirror flip
    's'       : Save current frame snapshot to disk
"""

import argparse
import sys
import time
from collections import deque
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

# Ensure project root is in sys.path for importing NEXUS modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from raspberry_pi.vision.threaded_camera import ThreadedCamera
    THREADED_CAM_AVAILABLE = True
except ImportError:
    THREADED_CAM_AVAILABLE = False


# =============================================================================
# HUD Drawing Helper
# =============================================================================
def draw_camera_hud(
    frame: np.ndarray,
    fps: float,
    latency_ms: float,
    frame_idx: int,
    resolution_str: str,
    backend_str: str,
    is_flipped: bool
) -> np.ndarray:
    """
    Renders diagnostic HUD overlay with FPS, latency, resolution,
    frame counter, and center guide.
    """
    canvas = frame.copy()
    h, w = canvas.shape[:2]

    # 1. Top Banner Box
    banner_h = 65
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, canvas, 0.25, 0, canvas)
    cv2.line(canvas, (0, banner_h), (w, banner_h), (0, 255, 200), 2)

    # 2. FPS Color Coding (Green >= 25, Orange 15-24, Red < 15)
    if fps >= 25.0:
        fps_color = (0, 255, 100)      # Bright Green
    elif fps >= 15.0:
        fps_color = (0, 200, 255)      # Orange / Yellow
    else:
        fps_color = (0, 60, 255)       # Red

    # FPS Text
    fps_text = f"FPS: {fps:5.1f}"
    cv2.putText(canvas, fps_text, (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, fps_color, 2, cv2.LINE_AA)

    # Latency Text
    lat_text = f"Latency: {latency_ms:5.1f} ms"
    cv2.putText(canvas, lat_text, (200, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)

    # Backend & Resolution Sub-info
    sub_text = f"Backend: {backend_str} | Res: {resolution_str} | Frame #{frame_idx} | Flip: {'ON' if is_flipped else 'OFF'}"
    cv2.putText(canvas, sub_text, (15, 53),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)

    # 3. Center Crosshair Guide
    cx, cy = w // 2, h // 2
    cross_size = 18
    cv2.line(canvas, (cx - cross_size, cy), (cx + cross_size, cy), (0, 255, 200), 1, cv2.LINE_AA)
    cv2.line(canvas, (cx, cy - cross_size), (cx, cy + cross_size), (0, 255, 200), 1, cv2.LINE_AA)
    cv2.circle(canvas, (cx, cy), 4, (0, 255, 200), 1, cv2.LINE_AA)

    # 4. Bottom Controls Legend
    footer_y = h - 12
    footer_text = "Hotkeys: 'q'/ESC = Quit | 'm' = Toggle Mirror Flip | 's' = Save Snapshot"
    (tw, th), _ = cv2.getTextSize(footer_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
    cv2.rectangle(canvas, (10, h - 30), (tw + 20, h - 6), (15, 15, 15), -1)
    cv2.putText(canvas, footer_text, (15, footer_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA)

    return canvas


# =============================================================================
# Main Camera Test Loop
# =============================================================================
def run_camera_test(
    source: Union[int, str] = 0,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    use_threaded: bool = True,
    use_mjpeg: bool = False,
    flip: bool = True,
    show: bool = True,
    save_dir: Optional[Path] = None
):
    print("=" * 65)
    print("NEXUS PERSON FOLLOWER ROBOT — LIVE CAMERA BENCHMARK")
    print("=" * 65)

    is_camera = str(source).isdigit()
    src_id = int(source) if is_camera else source

    backend_label = "ThreadedCamera" if (use_threaded and THREADED_CAM_AVAILABLE) else "OpenCV VideoCapture"
    format_label = "MJPG" if use_mjpeg else "YUYV"
    if backend_label == "ThreadedCamera":
        backend_full_label = f"Threaded ({format_label})"
    else:
        backend_full_label = f"Standard ({format_label})"

    print(f"[*] Camera Source : {source} (Index: {src_id})")
    print(f"[*] Backend       : {backend_full_label}")
    print(f"[*] Requested Res : {width}x{height} @ {fps} FPS")
    print(f"[*] Mirror Flip   : {'ENABLED' if flip else 'DISABLED'}")
    print(f"[*] GUI Preview   : {'ENABLED' if show else 'DISABLED (Headless)'}")
    print("=" * 65)

    # 1. Initialize Capture Device
    cap = None
    if use_threaded and THREADED_CAM_AVAILABLE:
        print("[CameraTest] Initializing High-Speed Threaded Camera...")
        cap = ThreadedCamera(
            source=src_id,
            width=width,
            height=height,
            fps=fps,
            use_mjpeg=use_mjpeg
        ).start()
    else:
        if use_threaded and not THREADED_CAM_AVAILABLE:
            print("[CameraTest] ⚠️ ThreadedCamera module not found, falling back to cv2.VideoCapture.")
        print("[CameraTest] Initializing standard OpenCV VideoCapture...")
        cap = cv2.VideoCapture(src_id)
        if use_mjpeg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        else:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)

    is_opened = cap.is_opened() if hasattr(cap, "is_opened") else cap.isOpened()
    if not is_opened:
        print(f"\n[ERROR] Failed to open camera device '{source}'.")
        print("        - Ensure webcam is connected to USB port.")
        print("        - Check with command: v4l2-ctl --list-devices or ls -l /dev/video*")
        return

    # 2. Performance Tracking Variables
    fps_history = deque(maxlen=30)
    latency_history = []
    frame_idx = 0
    start_test_time = time.perf_counter()
    last_frame_time = time.perf_counter()
    is_flipped = flip

    actual_res_str = f"{width}x{height}"

    print("\n[CameraTest] Streaming started. Press 'q' or 'ESC' to stop.")
    print("-----------------------------------------------------------------")

    try:
        while True:
            t_frame_start = time.perf_counter()

            # Read frame
            ret, frame = cap.read()
            if not ret or frame is None:
                if is_camera:
                    time.sleep(0.002)
                    continue
                break

            actual_h, actual_w = frame.shape[:2]
            actual_res_str = f"{actual_w}x{actual_h}"

            # Optional horizontal mirror flip
            if is_flipped:
                frame = cv2.flip(frame, 1)

            # Compute frame latency & FPS
            t_frame_end = time.perf_counter()
            latency_ms = (t_frame_end - t_frame_start) * 1000.0
            latency_history.append(latency_ms)

            # Time elapsed since last frame
            frame_delta = t_frame_end - last_frame_time
            last_frame_time = t_frame_end
            instant_fps = (1.0 / frame_delta) if frame_delta > 0 else 0.0

            fps_history.append(instant_fps)
            avg_fps = sum(fps_history) / len(fps_history)

            frame_idx += 1

            # Real-time console telemetry (in-place print)
            term_str = (
                f"\r[LIVE CAM] Frame: {frame_idx:05d} | "
                f"FPS: {avg_fps:5.1f} | "
                f"Latency: {latency_ms:5.1f} ms | "
                f"Res: {actual_res_str} | "
                f"Mode: {backend_full_label}"
            )
            sys.stdout.write(term_str)
            sys.stdout.flush()

            # Render GUI
            if show:
                annotated = draw_camera_hud(
                    frame=frame,
                    fps=avg_fps,
                    latency_ms=latency_ms,
                    frame_idx=frame_idx,
                    resolution_str=actual_res_str,
                    backend_str=backend_full_label,
                    is_flipped=is_flipped
                )

                cv2.imshow("NEXUS — Live Camera Benchmark", annotated)
                key = cv2.waitKey(1) & 0xFF

                if key in [ord("q"), 27]:  # 'q' or ESC
                    print("\n\n[CameraTest] User requested stop.")
                    break
                elif key in [ord("m"), ord("M")]:
                    is_flipped = not is_flipped
                    print(f"\n[Mirror Toggle] Flip: {'ENABLED' if is_flipped else 'DISABLED'}")
                elif key in [ord("s"), ord("S")]:
                    # Save snapshot
                    save_folder = save_dir or PROJECT_ROOT
                    snap_name = f"camera_test_{int(time.time())}.jpg"
                    snap_path = save_folder / snap_name
                    cv2.imwrite(str(snap_path), frame)
                    print(f"\n[Snapshot Saved] -> {snap_path}")

    except KeyboardInterrupt:
        print("\n\n[CameraTest] KeyboardInterrupt caught.")
    finally:
        # Cleanup
        if hasattr(cap, "stop"):
            cap.stop()
        elif hasattr(cap, "release"):
            cap.release()

        if show:
            cv2.destroyAllWindows()

        # Benchmark Summary
        total_test_time = time.perf_counter() - start_test_time
        overall_avg_fps = (frame_idx / total_test_time) if total_test_time > 0 else 0.0

        print("\n" + "=" * 65)
        print("NEXUS CAMERA BENCHMARK SUMMARY")
        print("=" * 65)
        print(f"Total Test Duration : {total_test_time:.2f} s")
        print(f"Total Frames Read   : {frame_idx} frames")
        print(f"Overall Average FPS : {overall_avg_fps:.2f} FPS")

        if latency_history:
            avg_lat = sum(latency_history) / len(latency_history)
            min_lat = min(latency_history)
            max_lat = max(latency_history)
            print(f"Latency (Avg)       : {avg_lat:.2f} ms")
            print(f"Latency (Min)       : {min_lat:.2f} ms")
            print(f"Latency (Max)       : {max_lat:.2f} ms")
        print(f"Final Resolution    : {actual_res_str}")
        print(f"Backend Used        : {backend_full_label}")
        print("=" * 65)


# =============================================================================
# CLI Entry Point
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="NEXUS Person Follower Robot — Live Camera Test & Latency / FPS Benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--source", "-s", type=str, default="0",
        help="Camera device index (e.g. '0') or video file path"
    )
    parser.add_argument(
        "--width", type=int, default=640,
        help="Requested frame width in pixels"
    )
    parser.add_argument(
        "--height", type=int, default=480,
        help="Requested frame height in pixels"
    )
    parser.add_argument(
        "--fps", type=int, default=30,
        help="Requested target framerate"
    )
    parser.add_argument(
        "--standard", action="store_true",
        help="Use standard blocking cv2.VideoCapture instead of high-speed ThreadedCamera"
    )
    parser.add_argument(
        "--mjpeg", action="store_true",
        help="Request MJPEG camera stream instead of clean uncompressed YUYV"
    )
    parser.add_argument(
        "--no-flip", action="store_true",
        help="Disable horizontal mirror flip (keep raw camera sensor orientation)"
    )
    parser.add_argument(
        "--no-view", action="store_true",
        help="Run headless without opening a GUI window (console logs only)"
    )
    parser.add_argument(
        "--save-dir", type=str, default=None,
        help="Directory to save snapshot images (defaults to project root)"
    )

    args = parser.parse_args()

    save_dir_path = Path(args.save_dir) if args.save_dir else None

    run_camera_test(
        source=args.source,
        width=args.width,
        height=args.height,
        fps=args.fps,
        use_threaded=not args.standard,
        use_mjpeg=args.mjpeg,
        flip=not args.no_flip,
        show=not args.no_view,
        save_dir=save_dir_path
    )


if __name__ == "__main__":
    main()
