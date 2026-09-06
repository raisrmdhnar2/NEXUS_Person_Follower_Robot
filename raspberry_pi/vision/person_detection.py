"""
NEXUS Person Follower Robot — Person Detection Module
======================================================
Module Path: raspberry_pi/vision/person_detection.py
Adheres to:
- docs/3_software_design/module_specification.md (Section 6: vision/person_detection.py)
- docs/3_software_design/interface_spesification.md (Section 3.1: PersonDetection)
- docs/3_software_design/configuration_spesification.md (Section 4: Person Detection)

Responsibility:
    Detect people in camera frames using the exported YOLO model.
    Decouples raw Ultralytics engine results from downstream NEXUS modules.

Input:
    Image Frame (numpy.ndarray BGR)

Output:
    list[PersonDetection]
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional
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
        bbox (tuple[int, int, int, int]): (x1, y1, x2, y2) in integer pixel coordinates.
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
        """Centroid (xc, yc) in pixel coordinates used by the follow controller."""
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict:
        return {
            "bbox": list(self.bbox),
            "confidence": round(float(self.confidence), 4),
            "class_id": int(self.class_id),
            "center": [round(c, 2) for c in self.center],
            "area": self.area
        }


# =============================================================================
# 2. PersonDetector Class
# =============================================================================
class PersonDetector:
    """
    YOLO Person Detection Module for the NEXUS robot.
    """

    def __init__(
        self,
        model_path: Optional[Path] = None,
        conf_threshold: float = 0.50,
        iou_threshold: float = 0.45,
        img_size: int = 640,
        device: Optional[str] = None
    ):
        if not ULTRALYTICS_AVAILABLE:
            raise ImportError(
                "The 'ultralytics' package is not installed in the active environment.\n"
                "Please run: pip install ultralytics"
            )

        self.model_path = self._resolve_model_path(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.img_size = img_size
        self.device = device or "cpu"

        print(f"[PersonDetector] Loading YOLO model from: {self.model_path}")
        self.model = YOLO(str(self.model_path), task="detect")

        # Dynamically verify person class ID (default is 0 in COCO)
        self.person_class_id = 0
        if hasattr(self.model, "names") and isinstance(self.model.names, dict):
            for cid, name in self.model.names.items():
                if name.lower() == "person":
                    self.person_class_id = int(cid)
                    break

        print(f"[PersonDetector] Initialized -> Class 'person': ID {self.person_class_id} | Device: {self.device}")

    @staticmethod
    def _resolve_model_path(requested_path: Optional[Path]) -> Path:
        """Locates the exported YOLO model if no path is explicitly provided."""
        if requested_path:
            p = Path(requested_path)
            if p.exists():
                return p
            raise FileNotFoundError(f"Requested model path '{requested_path}' does not exist.")

        # Search relative to repository root
        base_dir = Path(__file__).resolve().parent.parent.parent
        candidates = [
            base_dir / "models" / "yolo" / "exports" / "nexus_person_detector.onnx",
            base_dir / "models" / "yolo" / "exports" / "nexus_person_detector.pt",
            base_dir / "models" / "yolo" / "yolov8n.onnx",
            base_dir / "models" / "yolo" / "yolov8n.pt",
        ]
        for cand in candidates:
            if cand.exists():
                return cand

        raise FileNotFoundError(
            "Could not locate an exported YOLO model.\n"
            "Expected at: models/yolo/exports/nexus_person_detector.onnx"
        )

    def detect(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Detect human persons in an input frame.

        Args:
            frame: BGR image frame (H, W, 3).

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

