"""
NEXUS Person Follower Robot — Remote Person Detector (Client Module)
===================================================================
Module Path: raspberry_pi/vision/remote_person_detector.py

Tujuan:
    Menggantikan PersonDetector lokal di Raspberry Pi 4.
    Mengirimkan frame terkompresi (JPEG) ke Server GPU (AI Hub UB / VS Code Dev Tunnels),
    lalu mengubah hasil deteksi server menjadi List[PersonDetection] standar NEXUS.
"""

import time
import threading
import urllib.request
import urllib.error
import json
from typing import List, Tuple, Optional

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    CV2_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False

from raspberry_pi.vision.person_detection import PersonDetection


class RemotePersonDetector:
    """
    Klien deteksi orang jarak jauh via HTTP REST API.
    Memiliki interface yang identik dengan PersonDetector lokal (`detect(frame)`).
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8000",
        target_size: Tuple[int, int] = (320, 240),
        jpeg_quality: int = 75,
        timeout: float = 2.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.predict_url = f"{self.server_url}/predict"
        self.health_url = f"{self.server_url}/health"
        
        self.target_size = target_size
        self.jpeg_quality = jpeg_quality
        self.timeout = timeout
        
        self.encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality] if cv2 is not None else []
        self._last_error_time: float = 0.0
        self._is_server_alive: bool = True
        self.last_rtt_ms: float = 0.0

        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
        else:
            self.session = None

    def check_health(self) -> Tuple[bool, str]:
        """Memeriksa apakah server remote aktif dan dapat diakses."""
        try:
            if self.session is not None:
                resp = self.session.get(self.health_url, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    device = data.get("device_name", data.get("device", "Unknown"))
                    return True, f"Online ({device})"
            else:
                req = urllib.request.Request(self.health_url, method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        device = data.get("device_name", data.get("device", "Unknown"))
                        return True, f"Online ({device})"
        except Exception as e:
            return False, str(e)
        return False, "Unknown Error"

    def detect(self, frame: np.ndarray) -> List[PersonDetection]:
        """
        Mengirim frame ke server GPU dan mengembalikan list PersonDetection.
        Koordinat bounding box otomatis diskalakan kembali ke resolusi asli frame lokal.
        """
        if frame is None or frame.size == 0:
            return []

        orig_h, orig_w = frame.shape[:2]
        send_w, send_h = self.target_size

        if (orig_w, orig_h) != (send_w, send_h):
            small_frame = cv2.resize(frame, (send_w, send_h), interpolation=cv2.INTER_LINEAR)
        else:
            small_frame = frame

        success, encoded_img = cv2.imencode(".jpg", small_frame, self.encode_param)
        if not success:
            return []

        payload_bytes = encoded_img.tobytes()

        scale_x = orig_w / float(send_w)
        scale_y = orig_h / float(send_h)

        t_send = time.perf_counter()
        try:
            if self.session is not None:
                resp = self.session.post(
                    self.predict_url,
                    data=payload_bytes,
                    headers={"Content-Type": "image/jpeg"},
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.last_rtt_ms = (time.perf_counter() - t_send) * 1000.0
                    self._is_server_alive = True
                else:
                    return []
            else:
                req = urllib.request.Request(
                    self.predict_url,
                    data=payload_bytes,
                    headers={"Content-Type": "image/jpeg"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        self.last_rtt_ms = (time.perf_counter() - t_send) * 1000.0
                        self._is_server_alive = True
                    else:
                        return []

            results: List[PersonDetection] = []
            raw_dets = data.get("detections", [])
            for d in raw_dets:
                bx1, by1, bx2, by2 = d["bbox"]
                ax1 = int(round(bx1 * scale_x))
                ay1 = int(round(by1 * scale_y))
                ax2 = int(round(bx2 * scale_x))
                ay2 = int(round(by2 * scale_y))

                ax1 = max(0, min(orig_w - 1, ax1))
                ay1 = max(0, min(orig_h - 1, ay1))
                ax2 = max(ax1 + 1, min(orig_w, ax2))
                ay2 = max(ay1 + 1, min(orig_h, ay2))

                results.append(
                    PersonDetection(
                        bbox=(ax1, ay1, ax2, ay2),
                        confidence=float(d.get("confidence", 0.0)),
                        class_id=int(d.get("class_id", 0))
                    )
                )
            return results

        except Exception as e:
            now = time.time()
            if now - self._last_error_time > 5.0:
                print(f"[RemoteDetector WARNING] Gagal menghubungi server ({self.server_url}): {e}")
                self._last_error_time = now
            self._is_server_alive = False

        return []


class AsyncRemotePersonDetector:
    """
    Asynchronous Threaded Remote Detector.
    Menjalankan pengiriman frame ke server di thread latar belakang (background daemon).
    
    Keuntungan:
    - Main loop kamera, UI, dan pembacaan gestur tangan MediaPipe TIDAK PERNAH terblokir (tetap 30 FPS).
    - Maksimal hanya 1 request yang berjalan di jaringan (tidak ada antrean/traffic jam).
    - Mencegah Read Timeout di Microsoft Dev Tunnels.
    - Gestur Victory Sign (✌️) terbaca sangat sensitif dan cepat karena frame mengalir konstan.
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:8000",
        target_size: Tuple[int, int] = (320, 240),
        jpeg_quality: int = 70,
        timeout: float = 2.5,
        min_interval: float = 0.15,
    ):
        self.detector = RemotePersonDetector(
            server_url=server_url,
            target_size=target_size,
            jpeg_quality=jpeg_quality,
            timeout=timeout,
        )
        self.min_interval = min_interval
        self._pending_frame: Optional[np.ndarray] = None
        self._latest_detections: List[PersonDetection] = []
        self._lock = threading.Lock()
        self._running = True

        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    @property
    def last_rtt_ms(self) -> float:
        return self.detector.last_rtt_ms

    def check_health(self) -> Tuple[bool, str]:
        return self.detector.check_health()

    def submit_frame(self, frame: np.ndarray) -> None:
        """Menaruh frame terbaru untuk diproses oleh background thread."""
        if frame is not None and frame.size > 0:
            with self._lock:
                self._pending_frame = frame.copy()

    def get_latest_detections(self) -> List[PersonDetection]:
        """Mengambil hasil deteksi terakhir secara instan tanpa menunggu jaringan."""
        with self._lock:
            return list(self._latest_detections)

    def detect(self, frame: np.ndarray) -> List[PersonDetection]:
        """Drop-in replacement: Submit frame dan ambil deteksi terakhir secara non-blocking!"""
        self.submit_frame(frame)
        return self.get_latest_detections()

    def _worker_loop(self) -> None:
        last_req_time = 0.0
        while self._running:
            frame_to_process = None
            now = time.time()

            if (now - last_req_time) >= self.min_interval:
                with self._lock:
                    if self._pending_frame is not None:
                        frame_to_process = self._pending_frame
                        self._pending_frame = None

            if frame_to_process is not None:
                last_req_time = time.time()
                dets = self.detector.detect(frame_to_process)
                with self._lock:
                    if dets:
                        self._latest_detections = dets
            else:
                time.sleep(0.01)

    def stop(self) -> None:
        self._running = False
