#!/usr/bin/env python3
"""
NEXUS Person Follower Robot — Remote Connection Benchmark (test_remote_connection.py)
====================================================================================
File: test_remote_connection.py

Tujuan:
    Menguji koneksi, latensi (ping), dan akurasi inferensi dari Raspberry Pi
    ke Server GPU AI Hub UB (lewat URL Dev Tunnels VS Code / URL publik).

Penggunaan:
    python3 test_remote_connection.py --server https://xxxx-8000.asse.devtunnels.ms
    python3 test_remote_connection.py --server http://127.0.0.1:8000 --camera
"""

import argparse
import sys
import time
from pathlib import Path
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None

# Ensure root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import langsung dari file tanpa melalui __init__.py agar tidak memicu mediapipe
import importlib.util
spec = importlib.util.spec_from_file_location(
    "remote_person_detector",
    PROJECT_ROOT / "raspberry_pi" / "vision" / "remote_person_detector.py"
)
remote_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote_mod)
RemotePersonDetector = remote_mod.RemotePersonDetector


def main():
    parser = argparse.ArgumentParser(description="Benchmark Remote GPU Connection for NEXUS")
    parser.add_argument("--server", type=str, required=True, help="URL Server GPU (e.g. https://xxxx.devtunnels.ms)")
    parser.add_argument("--camera", action="store_true", help="Gunakan webcam untuk mengambil gambar uji nyata")
    parser.add_argument("--count", type=int, default=10, help="Jumlah frame uji coba (default: 10)")
    args = parser.parse_args()

    print("\n=======================================================")
    print("   NEXUS REMOTE GPU INFERENCE BENCHMARK TEST")
    print("=======================================================")
    print(f"Target Server URL: {args.server}")

    detector = RemotePersonDetector(server_url=args.server, target_size=(320, 240))

    # 1. Tes Health Check
    print("\n[Step 1] Memeriksa status kesehatan server (/health)...")
    is_alive, msg = detector.check_health()
    if not is_alive:
        print(f"❌ GAGAL: Server tidak dapat dijangkau!")
        print(f"Pesan Error: {msg}")
        print("\nPetunjuk:")
        print("1. Pastikan script 'server_yolo_gpu.py' sudah berjalan di server.")
        print("2. Di VS Code Tunnel, pastikan Port 8000 sudah di-forward dan Visibility diubah ke 'Public'.")
        print("3. Pastikan URL yang dimasukkan lengkap dengan protokol (http:// atau https://).")
        sys.exit(1)

    print(f"✅ BERHASIL: Server Online! Perangkat: {msg}")

    # 2. Siapkan Frame Uji
    if not CV2_AVAILABLE:
        print("\n⚠️ OpenCV/NumPy belum terpasang di host ini. Health check berhasil!")
        print("Untuk pengujian pengiriman frame gambar penuh, jalankan script ini di environment yang memiliki opencv-python.")
        sys.exit(0)

    frames = []
    if args.camera:
        print("\n[Step 2] Membuka webcam untuk mengambil frame nyata...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("⚠️ Gagal membuka webcam, menggunakan gambar sintetis.")
            for _ in range(args.count):
                frames.append(np.full((480, 640, 3), 128, dtype=np.uint8))
        else:
            for _ in range(args.count):
                ret, f = cap.read()
                if ret:
                    frames.append(f)
                time.sleep(0.05)
            cap.release()
    else:
        print("\n[Step 2] Menggunakan gambar sintetis (640x480)...")
        for i in range(args.count):
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.rectangle(img, (200, 100), (440, 400), (255, 255, 255), -1)
            frames.append(img)

    # 3. Jalankan Pengujian Latensi
    print(f"\n[Step 3] Mengirimkan {len(frames)} frame untuk mengukur Round-Trip Time (RTT)...")
    print("-" * 65)
    print(f"{'No':<5} | {'Status':<12} | {'Orang Terdeteksi':<18} | {'Latensi (RTT)':<15}")
    print("-" * 65)

    rtt_list = []
    for idx, f in enumerate(frames):
        t0 = time.perf_counter()
        detections = detector.detect(f)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        rtt_list.append(dt_ms)

        det_str = f"{len(detections)} orang" if detections else "0 (kosong)"
        status = "OK" if detections is not None else "TIMEOUT"

        print(f"#{idx+1:<4} | {status:<12} | {det_str:<18} | {dt_ms:.2f} ms")
        time.sleep(0.05)

    print("-" * 65)
    avg_rtt = sum(rtt_list) / len(rtt_list)
    min_rtt = min(rtt_list)
    max_rtt = max(rtt_list)

    print(f"\n📊 HASIL BENCHMARK LATENSI:")
    print(f" - Latensi Tercepat (Min) : {min_rtt:.2f} ms")
    print(f" - Latensi Rata-rata (Avg): {avg_rtt:.2f} ms (~{1000/avg_rtt:.1f} FPS ekuivalen)")
    print(f" - Latensi Terlama (Max)  : {max_rtt:.2f} ms")

    if avg_rtt < 80:
        print("\n🚀 KESIMPULAN: KONEKSI SANGAT BAIK! Sangat ideal untuk kendali robot follower.")
    elif avg_rtt < 150:
        print("\n👍 KESIMPULAN: KONEKSI CUKUP BAIK. Respons robot akan mulus dengan Fast Tracker lokal.")
    else:
        print("\n⚠️ KESIMPULAN: Latensi agak tinggi. Pastikan menggunakan Wi-Fi yang stabil.")
    print("=======================================================\n")


if __name__ == "__main__":
    main()
