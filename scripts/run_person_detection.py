#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — YOLO Person Detection Runner
===========================================================
This script runs the exported YOLO person detection model for the NEXUS robot.
It supports live webcam, pre-recorded video files, still images, and synthetic test frames.

Adheres to:
- docs/3_software_design/interface_spesification.md (Section 3.1: PersonDetection)
- docs/3_software_design/configuration_spesification.md (Section 4: Person Detection)

Usage examples:
    # Run with default exported ONNX model on webcam
    python3 scripts/run_person_detection.py

    # Run on a video file
    python3 scripts/run_person_detection.py --source path/to/video.mp4

    # Run on a single image and save the result
    python3 scripts/run_person_detection.py --source path/to/image.jpg --save output.jpg

    # Run in headless mode (no GUI window, logs to console)
    python3 scripts/run_person_detection.py --no-view
"""

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

import cv2
import numpy as np

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False


# =============================================================================
# 1. Interface Specification: PersonDetection Data Structure
# =============================================================================
@dataclass
class PersonDetection:
    """
    Standard NEXUS representation of a detected person.
    Matches docs/3_software_design/interface_spesification.md Section 3.1.

    Fields:
        bbox (tuple[int, int, int, int]): (x1, y1, x2, y2) in pixel coordinates.
        confidence (float): Detection confidence score in [0.0, 1.0].
        class_id (int): Detector class identifier (0 for person).
    """
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int

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
    def center(self) -> Tuple[float, float]:
        """Centroid (xc, yc) used by the NEXUS center follow controller."""
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def area(self) -> int:
        return self.width * self.height


# =============================================================================
# 2. PersonDetector Class
# =============================================================================
class PersonDetector:
    """
    YOLO-based person detector module for NEXUS.
    Encapsulates model loading and isolates Ultralytics from downstream modules.
    """

    def __init__(
        self,
        model_path: Path,
        conf_threshold: float = 0.50,
        iou_threshold: float = 0.45,
        img_size: int = 640,
        device: Optional[str] = None
    ):
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "The 'ultralytics' package is not installed.\n"
                "Please install it using: pip install ultralytics"
            )

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found at: {self.model_path}")

        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.device = device or ("cuda:0" if cv2.cuda.getCudaEnabledDeviceCount() > 0 else "cpu")

        print(f"[PersonDetector] Loading model from: {self.model_path}")
        self.model = YOLO(str(self.model_path), task="detect")

        # Resolve person class ID dynamically
        self.person_class_id = 0
        if hasattr(self.model, "names") and isinstance(self.model.names, dict):
            for cid, name in self.model.names.items():
                if name.lower() == "person":
                    self.person_class_id = int(cid)
                    break

        print(f"[PersonDetector] Target class: 'person' (ID: {self.person_class_id})")
        print(f"[PersonDetector] Device: {self.device} | Resolution: {self.img_size}x{self.img_size}")
        print(f"[PersonDetector] Thresholds -> Conf: {self.conf_threshold}, IoU: {self.iou_threshold}")

    def detect(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Run person detection on a single BGR frame.

        Args:
            frame: Input BGR image (H, W, 3).

        Returns:
            List[PersonDetection]: Clean list of detected persons.
        """
        if frame is None or frame.size == 0:
            return []

        results = self.model(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            imgsz=self.img_size,
            device=self.device,
            classes=[self.person_class_id],
            verbose=False
        )

        detections: List[PersonDetection] = []
        if not results:
            return detections

        first_res = results[0]
        if first_res.boxes is None:
            return detections

        h, w = frame.shape[:2]
        for box in first_res.boxes:
            cls_id = int(box.cls[0].item())
            if cls_id != self.person_class_id:
                continue

            conf = float(box.conf[0].item())
            xyxy = box.xyxy[0].tolist()

            x1 = max(0, int(round(xyxy[0])))
            y1 = max(0, int(round(xyxy[1])))
            x2 = min(w, int(round(xyxy[2])))
            y2 = min(h, int(round(xyxy[3])))

            if x2 > x1 and y2 > y1:
                detections.append(PersonDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    class_id=cls_id
                ))

        return detections


# =============================================================================
# 3. Visualization & Annotation Utilities
# =============================================================================
def draw_person_hud(
    frame: np.ndarray,
    detections: List[PersonDetection],
    latency_ms: Optional[float] = None,
    fps: Optional[float] = None,
    is_flipped: Optional[bool] = None
) -> np.ndarray:
    """
    Renders NEXUS-standard HUD annotations onto the image.
    """
    canvas = frame.copy()
    height, width = canvas.shape[:2]

    # Draw person detections
    for det in detections:
        x1, y1, x2, y2 = det.bbox

        # Bounding box (Neon Green)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Centroid crosshair (Red)
        cx, cy = int(det.center[0]), int(det.center[1])
        cv2.drawMarker(canvas, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 14, 2)

        # Confidence label tag
        label = f"person: {det.confidence:.1%}"
        font_scale = 0.5
        (lw, lh), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        tag_y1 = max(0, y1 - lh - baseline - 4)
        tag_y2 = y1
        cv2.rectangle(canvas, (x1, tag_y1), (x1 + lw + 6, tag_y2), (0, 255, 0), -1)
        cv2.putText(
            canvas, label, (x1 + 3, tag_y2 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA
        )

    # Top HUD Banner: Person Count
    count_text = f"NEXUS Person Count: {len(detections)}"
    cv2.rectangle(canvas, (10, 10), (280, 48), (30, 30, 30), -1)
    cv2.rectangle(canvas, (10, 10), (280, 48), (0, 255, 0), 1)
    cv2.putText(
        canvas, count_text, (20, 36),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA
    )

    # Mirror Mode Indicator (Top Right)
    if is_flipped is not None:
        flip_status = "Flip: ON" if is_flipped else "Flip: OFF"
        cv2.putText(
            canvas, f"{flip_status} (Press 'm')", (width - 190, 35),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255) if is_flipped else (180, 180, 180), 1, cv2.LINE_AA
        )

    # Bottom Telemetry Overlay (Latency & FPS)
    if latency_ms is not None:
        fps_text = f"{fps:.1f} FPS" if fps is not None else "-- FPS"
        telemetry_str = f"Latency: {latency_ms:.1f} ms | Speed: {fps_text}"
        cv2.rectangle(canvas, (10, height - 38), (320, height - 10), (30, 30, 30), -1)
        cv2.putText(
            canvas, telemetry_str, (16, height - 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1, cv2.LINE_AA
        )

    return canvas


# =============================================================================
# 4. Source Handlers (Image, Video, Webcam, Synthetic)
# =============================================================================
def run_image(
    detector: PersonDetector,
    image_path: Path,
    show: bool = True,
    save_path: Optional[Path] = None,
    flip: bool = False
):
    """Processes a single image file."""
    frame = cv2.imread(str(image_path))
    if frame is None:
        print(f"[ERROR] Could not read image at: {image_path}")
        return

    if flip:
        frame = cv2.flip(frame, 1)

    t0 = time.perf_counter()
    detections = detector.detect(frame)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[Result] Detected {len(detections)} person(s) in {latency_ms:.1f} ms:")
    for i, d in enumerate(detections, start=1):
        print(f"  #{i}: bbox={d.bbox}, conf={d.confidence:.2%}, center={d.center}")

    annotated = draw_person_hud(frame, detections, latency_ms=latency_ms, is_flipped=flip)

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(save_path), annotated)
        print(f"[Saved] Output saved to: {save_path}")

    if show:
        cv2.imshow("NEXUS Person Detector", annotated)
        print("Press any key in the image window to exit...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def run_video_stream(
    detector: PersonDetector,
    source: str,
    show: bool = True,
    save_path: Optional[Path] = None,
    flip: Optional[bool] = None
):
    """
    Processes a live webcam or video file stream.
    By default, webcams are flipped horizontally to avoid the mirror effect.
    """
    is_webcam = source.isdigit()
    if is_webcam:
        video_src = int(source)
        source_name = f"Camera #{video_src}"
    else:
        video_src = source
        source_name = f"File: {source}"

    # Default: webcam diflip horizontal (agar tidak mirror); file video tidak diflip kecuali diminta
    is_flipped = True if (flip is None and is_webcam) else bool(flip)

    print(f"\n[Stream] Opening video source: {source_name}...")
    print(f"[Stream] Horizontal flip (un-mirror): {'ENABLED' if is_flipped else 'DISABLED'} (Press 'm' during preview to toggle)")
    cap = cv2.VideoCapture(video_src)

    if not cap.isOpened():
        print(f"[ERROR] Failed to open video source: {source}")
        if source == "0":
            print("\n[TIP] If you do not have a physical webcam attached, you can test with:")
            print("  python3 scripts/run_person_detection.py --source synthetic")
            print("  python3 scripts/run_person_detection.py --source path/to/image.jpg")
        return

    writer = None
    if save_path:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        save_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(save_path), fourcc, fps_src, (w, h))

    print("[Stream] Processing loop started. Press 'q' or 'ESC' to quit, 'm' to toggle mirror flip.\n")

    fps_history = []
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[Stream] End of stream or frame read error.")
                break

            # Balik horizontal untuk mengatasi kamera mirror
            if is_flipped:
                frame = cv2.flip(frame, 1)

            t0 = time.perf_counter()
            detections = detector.detect(frame)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            fps = 1000.0 / latency_ms if latency_ms > 0 else 0.0
            fps_history.append(fps)
            if len(fps_history) > 30:
                fps_history.pop(0)
            avg_fps = sum(fps_history) / len(fps_history)

            annotated = draw_person_hud(
                frame, detections, latency_ms=latency_ms, fps=avg_fps, is_flipped=is_flipped
            )

            # Terminal log
            status_line = f"\r[NEXUS Vision] Persons: {len(detections):2d} | Latency: {latency_ms:5.1f} ms | FPS: {avg_fps:4.1f} | Flip: {'ON' if is_flipped else 'OFF'}"
            sys.stdout.write(status_line)
            sys.stdout.flush()

            if writer:
                writer.write(annotated)

            if show:
                cv2.imshow("NEXUS Person Detector", annotated)
                key = cv2.waitKey(1) & 0xFF
                if key in [ord("q"), 27]:  # 'q' or ESC
                    print("\n[Stream] User requested termination.")
                    break
                elif key in [ord("m"), ord("M")]:  # Toggle mirror mode on the fly
                    is_flipped = not is_flipped
                    state_str = "AKTIF (Un-mirrored / Flipped)" if is_flipped else "NONAKTIF (Original Sensor)"
                    print(f"\n[Mirror Toggle] Mode tampilan diubah ke: {state_str}")

    except KeyboardInterrupt:
        print("\n[Stream] Interrupted by user.")
    finally:
        cap.release()
        if writer:
            writer.release()
            print(f"[Saved] Video saved to: {save_path}")
        if show:
            cv2.destroyAllWindows()
        print("\n[Stream] Stream closed cleanly.")


def run_synthetic(detector: PersonDetector, show: bool = True):
    """Runs on a generated synthetic canvas with simulated human targets."""
    print("\n[Synthetic] Generating test canvas with simulated target...")
    frame = np.full((640, 640, 3), 210, dtype=np.uint8)

    # Draw background elements
    cv2.putText(frame, "NEXUS Test Canvas (Synthetic Target)", (60, 600),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 60, 60), 2)

    # Draw simulated human figure (head and body)
    cv2.circle(frame, (320, 200), 55, (100, 100, 100), -1)
    cv2.ellipse(frame, (320, 390), (90, 150), 0, 0, 360, (100, 100, 100), -1)

    t0 = time.perf_counter()
    detections = detector.detect(frame)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    annotated = draw_person_hud(frame, detections, latency_ms=latency_ms)
    print(f"[Synthetic] Complete in {latency_ms:.1f} ms. Detected: {len(detections)}")

    if show:
        cv2.imshow("NEXUS Synthetic Test", annotated)
        print("Press any key in the window to exit...")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


# =============================================================================
# 5. Model Resolver Helper
# =============================================================================
def resolve_model_path(requested_path: Optional[str]) -> Path:
    """Finds the model file, prioritizing exports/ then local root."""
    if requested_path:
        p = Path(requested_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Requested model path '{requested_path}' does not exist.")

    project_root = Path(__file__).resolve().parent.parent
    candidate_paths = [
        project_root / "models" / "yolo" / "exports" / "nexus_person_detector.onnx",
        project_root / "models" / "yolo" / "exports" / "nexus_person_detector.pt",
        project_root / "models" / "yolo" / "yolov8n.onnx",
        project_root / "models" / "yolo" / "yolov8n.pt",
    ]

    for cand in candidate_paths:
        if cand.exists():
            return cand

    raise FileNotFoundError(
        "Could not find any exported model!\n"
        "Expected at: models/yolo/exports/nexus_person_detector.onnx\n"
        "Please run models/yolo/yolo_person_detection.ipynb to export the model first."
    )


# =============================================================================
# 6. CLI Entry Point
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Run NEXUS Person Detection YOLO Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--model", "-m", type=str, default=None,
        help="Path to YOLO model (.onnx or .pt). Defaults to models/yolo/exports/nexus_person_detector.onnx"
    )
    parser.add_argument(
        "--source", "-s", type=str, default="0",
        help="Input source: camera index ('0'), video file path, image file path, or 'synthetic'"
    )
    parser.add_argument(
        "--conf", type=float, default=0.50,
        help="Detection confidence threshold"
    )
    parser.add_argument(
        "--iou", type=float, default=0.45,
        help="NMS IoU threshold"
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Inference image resolution"
    )
    parser.add_argument(
        "--no-view", action="store_true",
        help="Disable GUI window display (useful for headless servers/robots)"
    )
    parser.add_argument(
        "--save", type=str, default=None,
        help="Optional path to save output image or video"
    )
    parser.add_argument(
        "--flip", action="store_true", default=None,
        help="Force horizontal flip to fix mirror effect (default: True for webcam, press 'm' to toggle live)"
    )
    parser.add_argument(
        "--no-flip", action="store_true",
        help="Disable horizontal flip (keep raw camera sensor orientation)"
    )

    args = parser.parse_args()

    # Determine horizontal flip behavior
    flip_flag = None
    if args.no_flip:
        flip_flag = False
    elif args.flip:
        flip_flag = True

    # 1. Resolve model path
    try:
        model_file = resolve_model_path(args.model)
    except FileNotFoundError as err:
        print(f"[FATAL] {err}")
        sys.exit(1)

    # 2. Instantiate Detector
    try:
        detector = PersonDetector(
            model_path=model_file,
            conf_threshold=args.conf,
            iou_threshold=args.iou,
            img_size=args.imgsz
        )
    except Exception as e:
        print(f"[FATAL] Could not initialize detector: {e}")
        sys.exit(1)

    save_target = Path(args.save) if args.save else None
    show_window = not args.no_view

    # 3. Route execution by source type
    src = args.source.strip()
    if src.lower() == "synthetic":
        run_synthetic(detector, show=show_window)
    else:
        src_path = Path(src)
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        if src_path.exists() and src_path.is_file() and src_path.suffix.lower() in image_exts:
            run_image(detector, src_path, show=show_window, save_path=save_target, flip=bool(flip_flag))
        else:
            run_video_stream(detector, src, show=show_window, save_path=save_target, flip=flip_flag)


if __name__ == "__main__":
    main()

