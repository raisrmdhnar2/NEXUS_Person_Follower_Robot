# Panduan Menjalankan Server YOLO GPU (AI Hub UB via VS Code Tunnel)

File ini menjelaskan cara menjalankan backend AI di server Superkomputer / AI Hub UB agar Raspberry Pi 4 hanya bertindak sebagai client ringan (bebas dari lag / thermal throttling).

---

## 1. Persiapan di Server (Cukup Dilakukan Sekali)
Buka terminal server lewat VS Code Tunnel, lalu jalankan:

```bash
cd ~
# Masuk ke virtualenv Anda (jika ada), atau langsung install library:
pip install -r requirements.txt
```

Atau instal langsung paket intinya:
```bash
pip install ultralytics fastapi "uvicorn[standard]" python-multipart opencv-python-headless
```

---

## 2. Menjalankan Server YOLO GPU
Di terminal VS Code Tunnel:

```bash
python3 server_yolo_gpu.py --port 8000 --device cuda
```
*Output sukses:*
```text
[SERVER] Loading YOLO model: yolov8n.pt ...
[SERVER] Model running on: cuda:0 (NVIDIA ...)
[SERVER] Warmup complete. Ready to receive frames!
[SERVER] Starting HTTP service at http://0.0.0.0:8000
```

---

## 3. Forward Port di VS Code Menjadi "Public"
Agar Raspberry Pi bisa mengakses port 8000 lewat internet tanpa diblokir firewall kampus:

1. Di jendela VS Code, lihat panel bawah di sebelah tab **TERMINAL**, klik tab **PORTS**.
2. Klik tombol **Forward a Port** (jika belum otomatis muncul), ketik `8000` lalu tekan Enter.
3. Klik kanan pada baris port **8000** $\rightarrow$ pilih **Port Visibility** $\rightarrow$ ubah menjadi **Public**.
4. Salin alamat **Forwarded Address** yang muncul (contohnya: `https://xxxx-8000.asse.devtunnels.ms`).

---

## 4. Uji Koneksi dari Raspberry Pi
Di terminal Raspberry Pi (atau laptop):

```bash
python3 test_remote_connection.py --server https://xxxx-8000.asse.devtunnels.ms
```

---

## 5. Menjalankan Robot dengan Server Remote
Di terminal Raspberry Pi 4:

```bash
python3 top_module_remote.py --server https://xxxx-8000.asse.devtunnels.ms
```
