"""
NEXUS Person Follower Robot — Hand Gesture Recognition Module
==============================================================
Module Path: raspberry_pi/vision/gesture_recognition.py
Adheres to:
- docs/3_software_design/module_specification.md (Section 8: vision/gesture_recognition.py)
- docs/3_software_design/gesture_password_spesification.md (Password: Victory Sign ✌️)
- docs/3_software_design/interface_spesification.md (Section 5: GestureDetection)
- docs/3_software_design/configuration_spesification.md (Section 6: Gesture Password)

Responsibility:
    Detect hands in camera frames, track 21 3D landmarks via MediaPipe Hands,
    and classify whether the hand matches the NEXUS password: VICTORY SIGN ✌️.
    Strictly distinguishes Victory Sign from Open Palm (🖐️), Closed Fist (✊),
    pointing, and natural walking hand postures to prevent false triggers.
    Includes an OpenCV fallback detector if MediaPipe solutions is unavailable.

Input:
    Image Frame (numpy.ndarray BGR)

Output:
    list[GestureDetection]
"""

import math
import time
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional
import cv2
import numpy as np

# =============================================================================
# Robust MediaPipe Import Cascade (Tasks API for MediaPipe >= 0.10, legacy fallback)
# =============================================================================
mp_tasks_python = None
mp_tasks_vision = None
MEDIAPIPE_TASKS_AVAILABLE = False

mp_hands = None
mp_draw = None
MEDIAPIPE_AVAILABLE = False
_MEDIAPIPE_DIAGNOSTIC = ""

# 1. MediaPipe Tasks API (Preferred for MediaPipe 0.10.x / 1.0+)
try:
    import mediapipe as mp
    from mediapipe.tasks import python as _tp
    from mediapipe.tasks.python import vision as _tv
    mp_tasks_python = _tp
    mp_tasks_vision = _tv
    MEDIAPIPE_TASKS_AVAILABLE = True
    MEDIAPIPE_AVAILABLE = True
except Exception as _e_tasks:
    MEDIAPIPE_TASKS_AVAILABLE = False

# 2. MediaPipe Solutions API (Legacy fallback)
try:
    import mediapipe.python.solutions.hands as _h
    import mediapipe.python.solutions.drawing_utils as _d
    mp_hands = _h
    mp_draw = _d
    MEDIAPIPE_AVAILABLE = True
except Exception as _e1:
    try:
        import mediapipe as _mp
        if hasattr(_mp, "solutions") and hasattr(_mp.solutions, "hands"):
            mp_hands = _mp.solutions.hands
            mp_draw = _mp.solutions.drawing_utils
            MEDIAPIPE_AVAILABLE = True
    except Exception as _e2:
        pass


# =============================================================================
# 1. Interface Specification: GestureDetection Data Structure
# =============================================================================
@dataclass
class GestureDetection:
    """
    Standard NEXUS representation of a detected hand gesture.
    Matches docs/3_software_design/interface_spesification.md Section 5.

    Fields:
        gesture_type (str): "PASSWORD" (victory sign ✌️), "OTHER", or "NONE".
        confidence (float): Hand recognition confidence score in [0.0, 1.0].
        hand_bbox (tuple[int, int, int, int]): (x1, y1, x2, y2) in pixel coordinates.
        hand_center (tuple[float, float]): Hand centroid (xc, yc) in pixel coordinates.
        is_open_palm (bool): Set True if password gesture verified (retained for backward compatibility).
        handedness (str): "Left", "Right", or descriptive label (e.g. "Victory Sign ✌️").
        is_victory (bool): True if ✌️ Victory Sign is verified (Index & Middle extended, Ring & Pinky curled).
    """
    gesture_type: str
    confidence: float
    hand_bbox: Tuple[int, int, int, int]
    hand_center: Tuple[float, float]
    is_open_palm: bool
    handedness: str = "Unknown"
    is_victory: bool = False

    @property
    def x1(self) -> int:
        return self.hand_bbox[0]

    @property
    def y1(self) -> int:
        return self.hand_bbox[1]

    @property
    def x2(self) -> int:
        return self.hand_bbox[2]

    @property
    def y2(self) -> int:
        return self.hand_bbox[3]

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)


# =============================================================================
# 2. GestureRecognizer Class
# =============================================================================
class GestureRecognizer:
    """
    Hand Gesture Recognizer for NEXUS.
    Analyzes hand landmarks to detect the open-palm password.
    Includes multi-frame confirmation and cooldown to prevent false triggers.
    Falls back to OpenCV palm detection if MediaPipe solutions is unavailable.
    """

    def __init__(
        self,
        min_detection_confidence: float = 0.60,
        min_tracking_confidence: float = 0.50,
        required_consecutive_frames: int = 2,
        cooldown_seconds: float = 3.0
    ):
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.required_consecutive_frames = required_consecutive_frames
        self.cooldown_seconds = cooldown_seconds

        # Multi-frame state smoothing
        self._consecutive_password_frames: int = 0
        self._last_trigger_time: float = 0.0
        self.task_recognizer = None
        self.hands = None

        # Built-in OpenCV Haar face detector for accurate face exclusion fallback
        self.face_cascade = None
        try:
            if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
                face_xml = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
                if face_xml.exists():
                    cascade = cv2.CascadeClassifier(str(face_xml))
                    if not cascade.empty():
                        self.face_cascade = cascade
        except Exception:
            self.face_cascade = None

        # 1. MediaPipe Tasks AI Recognizer (Preferred - Pendekatan A)
        if MEDIAPIPE_TASKS_AVAILABLE and mp_tasks_python is not None:
            model_path = Path(__file__).resolve().parents[2] / "models" / "gesture" / "gesture_recognizer.task"
            if model_path.exists():
                try:
                    base_options = mp_tasks_python.BaseOptions(model_asset_path=str(model_path))
                    options = mp_tasks_vision.GestureRecognizerOptions(
                        base_options=base_options,
                        num_hands=2,
                        min_hand_detection_confidence=self.min_detection_confidence,
                        min_hand_presence_confidence=self.min_tracking_confidence
                    )
                    self.task_recognizer = mp_tasks_vision.GestureRecognizer.create_from_options(options)
                    print("[GestureRecognizer] MediaPipe Tasks AI Recognizer INITIALIZED successfully!")
                    print(f"                     Model: {model_path.name}")
                except Exception as e:
                    print(f"[GestureRecognizer] MediaPipe Tasks initialization warning: {e}")
                    self.task_recognizer = None

        # 2. MediaPipe Solutions Legacy Hands API
        if self.task_recognizer is None and MEDIAPIPE_AVAILABLE and mp_hands is not None:
            try:
                self.hands = mp_hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                print("[GestureRecognizer] MediaPipe Solutions Legacy Hands initialized successfully.")
            except Exception as e:
                print(f"[GestureRecognizer] MediaPipe Hands initialization warning: {e}")
                self.hands = None

        if self.task_recognizer is None and self.hands is None:
            print("[GestureRecognizer] NOTICE: MediaPipe is not accessible.")
            print("                     Active Mode: OpenCV Skin & Convexity Defect Palm Detector.")
            print("                     Face Exclusion: ACTIVE (Haar Cascade + Person Region Filter).")
            print("                     (Tip: You can also press 'p' on keyboard to toggle password).")

    def detect(self, frame: np.ndarray, persons: Optional[List] = None) -> List[GestureDetection]:
        """
        Detect hands and classify gestures in a BGR frame.

        Args:
            frame: Input BGR image (H, W, 3).
            persons: Optional list of detected PersonDetection objects for face exclusion.

        Returns:
            List[GestureDetection]: List of detected hands and their gesture classifications.
        """
        if frame is None or frame.size == 0:
            return []

        # 1. MediaPipe Tasks AI Recognizer (Primary - Pendekatan A)
        if self.task_recognizer is not None:
            return self._detect_mediapipe_tasks(frame)

        # 2. MediaPipe Solutions Legacy Hands (Secondary)
        if self.hands is not None:
            return self._detect_mediapipe(frame)

        # 3. OpenCV Palm Contour Fallback (Tertiary)
        return self._detect_palm_opencv(frame, persons=persons)

    def detect_roi(
        self,
        frame: np.ndarray,
        target_bbox: Tuple[int, int, int, int]
    ) -> List[GestureDetection]:
        """
        Fast Crop-ROI Gesture Detection on Target Upper Body.
        Instead of processing the entire 640x480 frame, crops a small sub-image
        covering the target's chest, shoulders, and head where a raised hand is expected.
        Translates detected hand coordinates back to full-frame space.
        Speedup: ~10x faster than full-frame inference (~15 ms vs ~250 ms)!
        """
        if frame is None or frame.size == 0 or target_bbox is None:
            return []

        fh, fw = frame.shape[:2]
        tx1, ty1, tx2, ty2 = [int(v) for v in target_bbox]
        tw = tx2 - tx1
        th = ty2 - ty1

        if tw <= 15 or th <= 20:
            return []

        # Crop upper 65% of target body with horizontal padding for arm reach
        pad_x = int(0.30 * tw)
        rx1 = max(0, tx1 - pad_x)
        rx2 = min(fw, tx2 + pad_x)
        ry1 = max(0, ty1 - int(0.12 * th))
        ry2 = min(fh, ty1 + int(0.68 * th))

        if rx2 <= rx1 or ry2 <= ry1:
            return []

        crop = frame[ry1:ry2, rx1:rx2]
        if crop.size == 0:
            return []

        # Run recognition on small sub-image (extremely fast!)
        crop_gestures = self.detect(crop)
        if not crop_gestures:
            return []

        # Translate coordinates back to full frame
        translated_gestures: List[GestureDetection] = []
        for g in crop_gestures:
            hx1, hy1, hx2, hy2 = g.hand_bbox
            hcx, hcy = g.hand_center

            full_bbox = (hx1 + rx1, hy1 + ry1, hx2 + rx1, hy2 + ry1)
            full_center = (hcx + rx1, hcy + ry1)

            translated_gestures.append(GestureDetection(
                gesture_type=g.gesture_type,
                confidence=g.confidence,
                hand_bbox=full_bbox,
                hand_center=full_center,
                is_open_palm=g.is_open_palm,
                handedness=g.handedness,
                is_victory=getattr(g, 'is_victory', False)
            ))

        return translated_gestures

    def _detect_mediapipe_tasks(self, frame: np.ndarray) -> List[GestureDetection]:
        """
        MediaPipe Tasks Gesture Recognizer (Pendekatan A).
        Analyzes 21 3D landmarks and deep neural network gesture classifications.
        Strictly distinguishes Victory Sign (✌️) from Open Palm (🖐️), Closed Fist (✊),
        or natural walking hand movements.
        """
        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.task_recognizer.recognize(mp_image)

        detections: List[GestureDetection] = []
        if not result.hand_landmarks:
            return detections

        for idx, hand_lms in enumerate(result.hand_landmarks):
            # Coordinates of all 21 landmarks
            x_coords = [int(lm.x * w) for lm in hand_lms]
            y_coords = [int(lm.y * h) for lm in hand_lms]

            padding = 15
            x1 = max(0, min(x_coords) - padding)
            y1 = max(0, min(y_coords) - padding)
            x2 = min(w, max(x_coords) + padding)
            y2 = min(h, max(y_coords) + padding)

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0

            # MediaPipe predicted gesture category & score
            top_category = "None"
            top_score = 0.0
            if result.gestures and idx < len(result.gestures) and result.gestures[idx]:
                top_category = result.gestures[idx][0].category_name
                top_score = result.gestures[idx][0].score

            # Handedness (Left / Right)
            hand_label = "Unknown"
            if result.handedness and idx < len(result.handedness) and result.handedness[idx]:
                hand_label = result.handedness[idx][0].category_name

            # Landmark-level finger extension check
            wrist = hand_lms[0]

            # 1. Index (Tip 8, PIP 6)
            tip8 = hand_lms[8]
            pip6 = hand_lms[6]
            d_index_tip = math.hypot(tip8.x - wrist.x, tip8.y - wrist.y)
            d_index_pip = math.hypot(pip6.x - wrist.x, pip6.y - wrist.y)
            index_extended = (d_index_tip > d_index_pip * 1.10) and (tip8.y < pip6.y)

            # 2. Middle (Tip 12, PIP 10)
            tip12 = hand_lms[12]
            pip10 = hand_lms[10]
            d_mid_tip = math.hypot(tip12.x - wrist.x, tip12.y - wrist.y)
            d_mid_pip = math.hypot(pip10.x - wrist.x, pip10.y - wrist.y)
            middle_extended = (d_mid_tip > d_mid_pip * 1.10) and (tip12.y < pip10.y)

            # 3. Ring (Tip 16, PIP 14)
            tip16 = hand_lms[16]
            pip14 = hand_lms[14]
            d_ring_tip = math.hypot(tip16.x - wrist.x, tip16.y - wrist.y)
            d_ring_pip = math.hypot(pip14.x - wrist.x, pip14.y - wrist.y)
            ring_extended = (d_ring_tip > d_ring_pip * 1.15) and (tip16.y < pip14.y)

            # 4. Pinky (Tip 20, PIP 18)
            tip20 = hand_lms[20]
            pip18 = hand_lms[18]
            d_pky_tip = math.hypot(tip20.x - wrist.x, tip20.y - wrist.y)
            d_pky_pip = math.hypot(pip18.x - wrist.x, pip18.y - wrist.y)
            pinky_extended = (d_pky_tip > d_pky_pip * 1.15) and (tip20.y < pip18.y)

            # 5. Thumb (Tip 4, MCP 2)
            tip4 = hand_lms[4]
            mcp2 = hand_lms[2]
            d_thumb_tip = math.hypot(tip4.x - wrist.x, tip4.y - wrist.y)
            d_thumb_mcp = math.hypot(mcp2.x - wrist.x, mcp2.y - wrist.y)
            thumb_extended = d_thumb_tip > d_thumb_mcp * 1.15

            extended_count = sum([index_extended, middle_extended, ring_extended, pinky_extended, thumb_extended])

            # =========================================================================
            # Strict VICTORY SIGN (✌️) Criteria:
            # 1. MediaPipe model predicted 'Victory' OR landmarks strictly form 'V'
            # 2. Index and Middle MUST be extended
            # 3. Ring and Pinky MUST be folded / curled (NOT extended)
            # 4. Strictly EXCLUDE 'Open_Palm', 'Closed_Fist', 'Thumb_Up', 'Thumb_Down'
            # 5. Extended fingers must be 2 (or 3 if thumb is counted)
            # =========================================================================
            landmark_victory = (
                index_extended and
                middle_extended and
                (not ring_extended) and
                (not pinky_extended) and
                extended_count in [2, 3]
            )

            is_victory = False
            if top_category == "Victory":
                if not ring_extended and not pinky_extended:
                    is_victory = True
            elif landmark_victory and top_category not in ["Closed_Fist", "Open_Palm", "Thumb_Up", "Thumb_Down"]:
                is_victory = True

            # Determine UI label and classification
            if is_victory:
                confidence = max(top_score, 0.85) if top_category == "Victory" else 0.80
                display_label = "Victory Sign ✌️"
                gesture_type = "PASSWORD"
            elif top_category == "Open_Palm" or (extended_count >= 4):
                confidence = max(top_score, 0.70)
                display_label = "Open Palm 🖐️"
                gesture_type = "OTHER"
            elif top_category == "Closed_Fist" or extended_count <= 1:
                confidence = max(top_score, 0.70)
                display_label = "Closed Fist ✊"
                gesture_type = "OTHER"
            elif top_category != "None":
                confidence = max(top_score, 0.50)
                display_label = f"{top_category} ({extended_count} fingers)"
                gesture_type = "OTHER"
            else:
                confidence = 0.40
                display_label = f"Hand ({extended_count} fingers)"
                gesture_type = "OTHER"

            detections.append(GestureDetection(
                gesture_type=gesture_type,
                confidence=confidence,
                hand_bbox=(x1, y1, x2, y2),
                hand_center=(cx, cy),
                is_open_palm=is_victory,  # Set True if victory for backward compatibility
                handedness=display_label,
                is_victory=is_victory
            ))

        return detections

    def _detect_mediapipe(self, frame: np.ndarray) -> List[GestureDetection]:
        """MediaPipe Hands landmark detector."""
        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)

        detections: List[GestureDetection] = []
        if not results.multi_hand_landmarks:
            return detections

        handedness_list = []
        if results.multi_handedness:
            for hnd in results.multi_handedness:
                handedness_list.append(hnd.classification[0].label)

        for idx, hand_lms in enumerate(results.multi_hand_landmarks):
            h_label = handedness_list[idx] if idx < len(handedness_list) else "Unknown"

            x_coords = [int(lm.x * w) for lm in hand_lms.landmark]
            y_coords = [int(lm.y * h) for lm in hand_lms.landmark]

            padding = 15
            x1 = max(0, min(x_coords) - padding)
            y1 = max(0, min(y_coords) - padding)
            x2 = min(w, max(x_coords) + padding)
            y2 = min(h, max(y_coords) + padding)

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0

            is_victory, conf = self._is_victory_mediapipe(hand_lms.landmark)
            gesture_type = "PASSWORD" if is_victory else "OTHER"
            display_label = "Victory Sign ✌️" if is_victory else f"Hand ({h_label})"

            detections.append(GestureDetection(
                gesture_type=gesture_type,
                confidence=conf,
                hand_bbox=(x1, y1, x2, y2),
                hand_center=(cx, cy),
                is_open_palm=is_victory,
                handedness=display_label,
                is_victory=is_victory
            ))

        return detections

    def _is_victory_mediapipe(self, landmarks) -> Tuple[bool, float]:
        """Evaluates MediaPipe landmarks: confirms Victory Sign ✌️ (Index & Middle extended, Ring & Pinky folded)."""
        wrist = landmarks[0]

        # 1. Index finger (8, 6)
        tip8, pip6 = landmarks[8], landmarks[6]
        d_idx_tip = math.hypot(tip8.x - wrist.x, tip8.y - wrist.y)
        d_idx_pip = math.hypot(pip6.x - wrist.x, pip6.y - wrist.y)
        idx_ext = (d_idx_tip > d_idx_pip * 1.10) and (tip8.y < pip6.y)

        # 2. Middle finger (12, 10)
        tip12, pip10 = landmarks[12], landmarks[10]
        d_mid_tip = math.hypot(tip12.x - wrist.x, tip12.y - wrist.y)
        d_mid_pip = math.hypot(pip10.x - wrist.x, pip10.y - wrist.y)
        mid_ext = (d_mid_tip > d_mid_pip * 1.10) and (tip12.y < pip10.y)

        # 3. Ring finger (16, 14)
        tip16, pip14 = landmarks[16], landmarks[14]
        d_rng_tip = math.hypot(tip16.x - wrist.x, tip16.y - wrist.y)
        d_rng_pip = math.hypot(pip14.x - wrist.x, pip14.y - wrist.y)
        rng_ext = (d_rng_tip > d_rng_pip * 1.15) and (tip16.y < pip14.y)

        # 4. Pinky finger (20, 18)
        tip20, pip18 = landmarks[20], landmarks[18]
        d_pky_tip = math.hypot(tip20.x - wrist.x, tip20.y - wrist.y)
        d_pky_pip = math.hypot(pip18.x - wrist.x, pip18.y - wrist.y)
        pky_ext = (d_pky_tip > d_pky_pip * 1.15) and (tip20.y < pip18.y)

        is_victory = idx_ext and mid_ext and (not rng_ext) and (not pky_ext)
        confidence = 0.90 if is_victory else 0.40
        return is_victory, confidence

    def _is_open_palm_mediapipe(self, landmarks) -> Tuple[bool, float]:
        """Legacy helper retained for compatibility."""
        return self._is_victory_mediapipe(landmarks)

    def _detect_palm_opencv(self, frame: np.ndarray, persons: Optional[List] = None) -> List[GestureDetection]:
        """
        OpenCV fallback palm/hand detector.
        Uses dual-layer face exclusion (Haar Cascade + YOLO head region)
        and convexity defect / solidity analysis to detect open palm (🖐️).
        """
        h, w = frame.shape[:2]

        # 1. Build Face & Head Exclusion Zones
        face_exclusion_zones = []

        # Layer A: OpenCV Haar Cascade frontal face detection (fast downscaled)
        if self.face_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small_gray = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
                faces = self.face_cascade.detectMultiScale(
                    small_gray,
                    scaleFactor=1.25,
                    minNeighbors=4,
                    minSize=(30, 30)
                )
                for (fx, fy, fw, fh) in faces:
                    # Scale back to full frame and extend downwards to cover chin & neck
                    fx1 = max(0, int(fx * 2) - 15)
                    fy1 = max(0, int(fy * 2) - 15)
                    fx2 = min(w, int((fx + fw) * 2) + 15)
                    fy2 = min(h, int(fy * 2 + fh * 3.0))
                    face_exclusion_zones.append((fx1, fy1, fx2, fy2))
            except Exception:
                pass

        # Layer B: Geometric head & face exclusion zone from YOLO person detection
        if persons:
            for p in persons:
                # The upper-center 65% of detected person bbox is head/face/neck
                fx1 = max(0, p.x1 + int(p.width * 0.15))
                fy1 = max(0, p.y1 - 20)
                fx2 = min(w, p.x2 - int(p.width * 0.15))
                fy2 = min(h, p.y1 + int(p.height * 0.65))
                face_exclusion_zones.append((fx1, fy1, fx2, fy2))

        # 2. Skin segmentation in HSV color space
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_skin = np.array([0, 30, 50], dtype=np.uint8)
        upper_skin = np.array([25, 180, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower_skin, upper_skin)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.dilate(mask, kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections: List[GestureDetection] = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            # Minimum area for a visible hand (at least ~45x45 px)
            if area < 2000 or area > (h * w * 0.35):
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect_ratio = float(bw) / float(bh) if bh > 0 else 0
            if aspect_ratio < 0.25 or aspect_ratio > 2.5:
                continue

            cx = x + bw / 2.0
            cy = y + bh / 2.0

            # 3. EXCLUDE FACE: Discard contour if its center or box overlaps face zone
            is_face = False
            for (fx1, fy1, fx2, fy2) in face_exclusion_zones:
                if fx1 <= cx <= fx2 and fy1 <= cy <= fy2:
                    is_face = True
                    break
                # Check bounding box overlap
                ox1 = max(x, fx1)
                oy1 = max(y, fy1)
                ox2 = min(x + bw, fx2)
                oy2 = min(y + bh, fy2)
                if ox2 > ox1 and oy2 > oy1:
                    overlap_area = (ox2 - ox1) * (oy2 - oy1)
                    if overlap_area > 0.40 * (bw * bh):
                        is_face = True
                        break

            if is_face:
                continue  # Discard face detection

            # 4. Finger Valley Analysis using Convexity Defects & Solidity
            hull_points = cv2.convexHull(cnt, returnPoints=True)
            hull_area = cv2.contourArea(hull_points) if len(hull_points) > 2 else area
            solidity = float(area) / hull_area if hull_area > 0 else 1.0

            # Solid oval shape without finger gaps is not an open hand
            if solidity > 0.92:
                continue

            finger_valleys = 0
            epsilon = 0.012 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            test_contours = [approx, cnt]

            for c_test in test_contours:
                if len(c_test) > 3:
                    try:
                        hull_idx = cv2.convexHull(c_test, returnPoints=False)
                        if hull_idx is not None and len(hull_idx) > 3:
                            defects = cv2.convexityDefects(c_test, hull_idx)
                            if defects is not None:
                                current_valleys = 0
                                for i in range(defects.shape[0]):
                                    s, e, f, d = defects[i, 0]
                                    start = tuple(c_test[s][0])
                                    end = tuple(c_test[e][0])
                                    far = tuple(c_test[f][0])
                                    depth = d / 256.0

                                    # Valley between extended fingers
                                    if depth > 7.0:
                                        a = math.hypot(end[0] - start[0], end[1] - start[1])
                                        b = math.hypot(far[0] - start[0], far[1] - start[1])
                                        c = math.hypot(end[0] - far[0], end[1] - far[1])
                                        if b * c > 0:
                                            cos_val = max(-1.0, min(1.0, (b**2 + c**2 - a**2) / (2 * b * c)))
                                            angle = math.acos(cos_val)
                                            # V-sign angle between index and middle is typically 15 to 80 degrees
                                            if math.radians(15) <= angle <= math.radians(85):
                                                current_valleys += 1
                                finger_valleys = max(finger_valleys, current_valleys)
                                if finger_valleys >= 1:
                                    break
                    except Exception:
                        pass

            # 5. Victory Sign condition for OpenCV fallback:
            # - In Victory sign (✌️), 2 fingers extend upward, creating 1 prominent valley
            # - Aspect ratio H > W (bw / bh <= 0.90)
            # - Solidity: 0.55 <= solidity <= 0.88 (more compact than open palm)
            is_victory = (
                (finger_valleys in [1, 2]) and
                (0.55 <= solidity <= 0.88) and
                (aspect_ratio <= 0.90)
            )
            confidence = min(0.95, max(0.65, 0.60 + finger_valleys * 0.15)) if is_victory else 0.40

            detections.append(GestureDetection(
                gesture_type="PASSWORD" if is_victory else "OTHER",
                confidence=confidence,
                hand_bbox=(x, y, x + bw, y + bh),
                hand_center=(cx, cy),
                is_open_palm=is_victory,
                handedness="Victory Sign ✌️" if is_victory else "Hand",
                is_victory=is_victory
            ))

        return detections

    def check_password_event(self, detections: List[GestureDetection]) -> bool:
        """
        Determines if a valid password trigger event has occurred:
        - Confirms 2-frame persistence for fast responsiveness.
        - Enforces 3.0-second cooldown period to prevent rapid bouncing.

        Returns:
            bool: True if a state transition event should be triggered.
        """
        now = time.time()
        has_password = any(getattr(d, "is_victory", False) or d.is_open_palm for d in detections)

        if (now - self._last_trigger_time) < self.cooldown_seconds:
            self._consecutive_password_frames = 0
            return False

        if has_password:
            self._consecutive_password_frames += 1
            if self._consecutive_password_frames >= self.required_consecutive_frames:
                self._last_trigger_time = now
                self._consecutive_password_frames = 0
                return True
        else:
            self._consecutive_password_frames = max(0, self._consecutive_password_frames - 1)

        return False
