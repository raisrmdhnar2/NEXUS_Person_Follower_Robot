#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Remote GPU Inference Server (server_yolo_gpu.py)
=============================================================================
File: server/server_yolo_gpu.py

Tujuan:
    Dijalankan di Server Superkomputer (AI Hub UB / Cloud GPU).
    Menerima kiriman frame kamera (JPEG) dari Raspberry Pi via HTTP POST,
    melakukan inferensi YOLOv8 di GPU CUDA (< 5 ms), dan mengembalikan
    koordinat Bounding Box serta offset horizontal dx.

Cara Menjalankan di Server (via VS Code Tunnel):
    1. pip install -r requirements.txt
    2. python3 server_yolo_gpu.py --port 8000 --device cuda
    3. Di VS Code, buka tab PORTS -> Forward Port 8000 -> Set Visibility ke "Public".
"""

import argparse
import time
import io
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
import torch
from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from ultralytics import YOLO

# =============================================================================
# Inisialisasi FastAPI App
# =============================================================================
app = FastAPI(
    title="NEXUS YOLO GPU Inference Server",
    description="High-performance GPU offloading server for NEXUS Person Follower Robot",
    version="1.0.0"
)

# Izinkan CORS agar bisa diakses dari tunnel / client mana pun
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
model: Optional[YOLO] = None
device_name: str = "cpu"
active_device: str = "cpu"


def load_model(model_name: str = "yolov8n.pt", device: str = "auto") -> None:
    global model, device_name, active_device
    print(f"\n[SERVER] Loading YOLO model: {model_name} ...")
    
    # Deteksi GPU / CUDA
    if device == "auto":
        if torch.cuda.is_available():
            active_device = "cuda:0"
            device_name = torch.cuda.get_device_name(0)
        else:
            active_device = "cpu"
            device_name = "CPU"
    else:
        active_device = device
        device_name = torch.cuda.get_device_name(0) if "cuda" in device and torch.cuda.is_available() else device

    model = YOLO(model_name)
    # Warmup model di GPU
    print(f"[SERVER] Model running on: {active_device} ({device_name})")
    dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
    model.predict(source=dummy_img, device=active_device, classes=[0], verbose=False)
    print(f"[SERVER] Warmup complete. Ready to receive frames!\n")


@app.get("/")
@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Cek status kesehatan server dan info akselerator GPU."""
    cuda_avail = torch.cuda.is_available()
    gpu_mem = None
    if cuda_avail:
        gpu_mem = {
            "allocated_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024, 2),
            "reserved_mb": round(torch.cuda.memory_reserved(0) / 1024 / 1024, 2)
        }
    return {
        "status": "online",
        "service": "nexus_gpu_inference",
        "device": active_device,
        "device_name": device_name,
        "cuda_available": cuda_avail,
        "gpu_memory": gpu_mem,
        "timestamp": time.time()
    }


@app.post("/predict")
async def predict_frame(request: Request) -> Dict[str, Any]:
    """
    Endpoint utama inferensi deteksi orang:
    Menerima binary stream JPEG (Content-Type: image/jpeg atau octet-stream),
    mengembalikan daftar orang dan target person terbaik.
    """
    if model is None:
        raise HTTPException(status_code=503, detail="Model not initialized yet")

    t_start = time.perf_counter()

    # Baca raw body bytes
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty image payload")

    # Decode JPEG bytes ke numpy array (OpenCV BGR)
    nparr = np.frombuffer(body, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Failed to decode JPEG image")

    h, w, _ = frame.shape
    t_decode = time.perf_counter()

    # Jalankan YOLO di GPU (Hanya deteksi class 0 = Person)
    results = model.predict(
        source=frame,
        device=active_device,
        classes=[0],
        conf=0.40,
        imgsz=320,
        verbose=False
    )
    t_infer = time.perf_counter()

    detections: List[Dict[str, Any]] = []
    best_target: Optional[Dict[str, Any]] = None
    max_area = 0.0

    if results and len(results) > 0:
        boxes = results[0].boxes
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = [int(val) for val in xyxy]
                conf = float(box.conf[0].cpu().numpy())
                
                # Filter batas frame
                x1 = max(0, min(w - 1, x1))
                y1 = max(0, min(h - 1, y1))
                x2 = max(x1 + 1, min(w, x2))
                y2 = max(y1 + 1, min(h, y2))

                det_dict = {
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(conf, 4),
                    "class_id": 0
                }
                detections.append(det_dict)

                # Prioritaskan target dengan bounding box terbesar (orang terdekat)
                area = (x2 - x1) * (y2 - y1)
                if area > max_area:
                    max_area = area
                    cx = (x1 + x2) / 2.0
                    # Hitung dx ternormalisasi [-1.0 s/d +1.0] dari tengah frame
                    dx = (cx - (w / 2.0)) / (w / 2.0)
                    best_target = {
                        "bbox": [x1, y1, x2, y2],
                        "dx": round(float(dx), 4),
                        "confidence": round(conf, 4),
                        "area": int(area)
                    }

    t_end = time.perf_counter()

    return {
        "status": "ok",
        "detected": len(detections) > 0,
        "num_persons": len(detections),
        "detections": detections,
        "best_target": best_target,
        "timing_ms": {
            "decode": round((t_decode - t_start) * 1000, 2),
            "inference": round((t_infer - t_decode) * 1000, 2),
            "total": round((t_end - t_start) * 1000, 2)
        }
    }


def main():
    parser = argparse.ArgumentParser(description="NEXUS Remote YOLO GPU Inference Server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Ultralytics model (default: yolov8n.pt)")
    parser.add_argument("--device", type=str, default="auto", help="Device to run model (auto, cuda, cpu)")
    args = parser.parse_args()

    load_model(model_name=args.model, device=args.device)

    print(f"[SERVER] Starting HTTP service at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
