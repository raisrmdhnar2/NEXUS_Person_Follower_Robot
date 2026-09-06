# NEXUS YOLO Person Detection Module

## 1. Module Overview
This directory contains the YOLO-based person detection model development assets for the **NEXUS Person Follower Robot** (inspired by Karen from SpongeBob SquarePants, Department of Technology and Information, Brawijaya University).

The module is strictly scoped to person detection:
```text
Camera Frame ---> YOLO Detection ---> Filter 'person' ---> PersonDetection[]
```

## 2. Model Specifications
- **Architecture**: yolov8n.pt
- **Framework**: Ultralytics YOLO / PyTorch
- **Input Resolution**: 640x640
- **Target Class**: `person` (Class ID 0)
- **Confidence Threshold**: 0.5
- **IoU Threshold**: 0.45
- **Baseline Precision**: FP32

## 3. Directory Layout
- `yolo_person_detection.ipynb`: Primary development, evaluation, and export notebook.
- `datasets/`: Storage for custom person datasets (YOLO annotation format).
- `weights/`: Downloaded pretrained weights.
- `runs/`: Training and validation run outputs.
- `exports/`: Exported PyTorch (`.pt`), ONNX (`.onnx`), and metadata (`model_info.json`).

## 4. Status
- **Training Status**: Pretrained Baseline (Custom training disabled by default)
- **Deployment Target**: Raspberry Pi 5
- **Raspberry Pi 5 Benchmark**: NOT YET BENCHMARKED
