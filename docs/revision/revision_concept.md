# Dokumen Revisi Konsep: Kontrol Gerak & Komunikasi NEXUS
================================================================

**Dokumen Versi**: 1.0  
**Tanggal**: 2026-09-07  
**Status**: Disetujui (Approved)  
**Target Modul**: 
- Raspberry Pi 5 (`top_module.py`, `esp32_uart.py`)
- ESP32 Motor Firmware (`esp32/`)

---

## 1. Latar Belakang & Motivasi Perubahan

Pada konsep perancangan awal, Raspberry Pi 5 direncanakan menghitung seluruh setpoint kecepatan linier ($v$) dan kecepatan sudut ($\omega$) dari kamera, kemudian mengirimkan nilai kecepatan kedua roda ($v_L, v_R$) ke ESP32.

Namun, pendekatan tersebut memiliki beberapa kelemahan di lapangan:
1. **Latensi Sensor Jarak pada OS Linux**: Membaca sensor jarak fisik (seperti Ultrasonik atau ToF) melalui Raspberry Pi rentan mengalami *jitter* dan keterlambatan akibat mekanisme penjadwalan sistem operasi (*non-real-time OS*).
2. **Keamanan / Refleks Darurat Kurang Cepat**: Jika ada halangan mendadak di depan robot, pengereman darurat (*hard-brake*) lebih aman dan cepat dieksekusi langsung oleh mikrokontroler (*bare-metal/FreeRTOS*).
3. **Beban Komputasi Raspberry Pi**: Raspberry Pi sebaiknya difokuskan sepenuhnya pada inferensi AI (*YOLO Person Detection*, *MediaPipe 3D Landmark Gesture*, dan *Target Tracking/Locking*) agar *framerate* kamera tetap tinggi (~30 FPS).

### Konsep Baru (Decoupled Architecture)
Tugas dibagi secara tegas dan modular:
* **Raspberry Pi 5**: Bertindak sebagai **"Mata & Otak Strategis"** yang hanya menentukan arah orientasi target terhadap kamera (kiri, kanan, atau tengah) dan status robot (ON/OFF).
* **ESP32**: Bertindak sebagai **"Kaki & Refleks Sensoris"** yang membaca sensor jarak fisik secara *real-time*, menghitung kecepatan motor dengan PID, serta mengambil keputusan maju, mundur, atau berhenti darurat.

---

## 2. Pemisahan Tanggung Jawab (*Separation of Concerns*)

```
┌────────────────────────────────────────────────────────┐
│                   RASPBERRY PI 5                       │
│  - Image Acquisition & Camera Unmirror                 │
│  - YOLOv8 Person Detection                             │
│  - MediaPipe Gesture Recognition (Open Palm 🖐️)        │
│  - IoU Multi-Person Tracking (Track ID: 1, 2, ...)     │
│  - Target Locking & Anti-Hijack                        │
│  - 3.0s Auto-Loss Timeout (NEXUS ON -> NEXUS OFF)      │
│  - Deadzone Steering Evaluator (dx -> -, x, +)         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │ UART Serial (1-Byte Code: '-', 'x', '+', 's')
                           │ Baudrate: 115200 bps
                           ▼
┌────────────────────────────────────────────────────────┐
│                        ESP32                           │
│  - Real-Time Hardware Distance Sensor (Ultrasonic/ToF) │
│  - Steering Execution (Turn Left / Turn Right)         │
│  - Distance Regulation (Forward / Reverse / Hold)      │
│  - Optical/Magnetic Wheel Encoder Feedback             │
│  - Closed-Loop Motor PID Control & PWM Generation      │
│  - Watchdog Safety Timer (Auto-Stop if Serial Lost)    │
└────────────────────────────────────────────────────────┘
```

---

## 3. Spesifikasi Protokol Serial UART (Pi $\to$ ESP32)

Komunikasi menggunakan jalur Serial UART dengan ukuran payload sangat ringan (1 karakter ASCII per siklus kendali).

### Definisi Kode Arah & Status

| Karakter | Arti Simbol | Kondisi di Raspberry Pi | Perilaku Motor di ESP32 |
| :---: | :--- | :--- | :--- |
| `'-'` | **Kiri** (*Turn Left*) | NEXUS ON, Target berada di sebelah kiri kamera ($dx < -0.15$) | Putar badan ke kiri (Roda kanan maju, roda kiri mundur/pelan). |
| `'+'` | **Kanan** (*Turn Right*) | NEXUS ON, Target berada di sebelah kanan kamera ($dx > +0.15$) | Putar badan ke kanan (Roda kiri maju, roda kanan mundur/pelan). |
| `'x'` | **Center Point** (*Target Lurus*) | NEXUS ON, Target berada di area tengah layar ($-0.15 \le dx \le +0.15$) | Menghadap lurus. ESP32 membaca sensor jarak untuk maju/menjaga jarak ideal. |
| `'s'` | **STOP / Standby** | NEXUS OFF, Target belum terkunci, Target hilang, atau deactivation | Matikan kedua motor seketika ($PWM = 0$). |

---

## 4. Logika di Sisi Raspberry Pi 5

Raspberry Pi mengevaluasi nilai penyimpangan horizontal target ($dx$) dari titik tengah frame:
$$\text{center\_x} = \frac{x_1 + x_2}{2}$$
$$dx = \frac{\text{center\_x} - \frac{W}{2}}{\frac{W}{2}} \quad \in [-1.0, +1.0]$$

### Konsep Deadzone (Toleransi Tengah)
Untuk mencegah fenomena *hunting oscillation* (robot bergoyang/bergetar ke kiri dan ke kanan secara kasar akibat pergerakan alami tubuh manusia), diterapkan batas toleransi tengah (*deadzone*):

$$\text{THRESHOLD\_DEADZONE} = 0.15 \quad (\pm 15\% \text{ dari tengah layar})$$

```python
def determine_steering_command(state, target_manager, target_person) -> str:
    # 1. Jika robot dalam keadaan OFF atau target tidak terkunci / hilang
    if state != NexusState.ON or not target_manager.is_target_present:
        return 's'

    # 2. Ambil nilai dx dari target yang terkunci
    dx = target_person.get_dx_normalized(frame_width)

    # 3. Klasifikasi arah berdasarkan deadzone
    if dx < -0.15:
        return '-'   # Target di kiri -> Belok Kiri
    elif dx > 0.15:
        return '+'   # Target di kanan -> Belok Kanan
    else:
        return 'x'   # Target sudah di tengah -> Siap maju/jaga jarak
```

---

## 5. Logika di Sisi ESP32 (Firmware Motor & Jarak)

Ketika ESP32 menerima perintah dari Raspberry Pi:

### A. Jika Perintah adalah `'s'` (STOP)
* Nonaktifkan driver motor (PWM = 0).
* Set status robot ke kondisi *Idle/Standby*.

### B. Jika Perintah adalah `'-'` (Belok Kiri) atau `'+'` (Belok Kanan)
* ESP32 memprioritaskan penyelarasan sudut (*angular alignment*):
  * `'-'`: Roda kiri mundur/pelan, roda kanan maju $\to$ Robot berputar ke kiri di tempat.
  * `'+'`: Roda kanan mundur/pelan, roda kiri maju $\to$ Robot berputar ke kanan di tempat.
* Kecepatan putar diatur pada kecepatan konstan yang nyaman (misal 30% - 40% PWM).

### C. Jika Perintah adalah `'x'` (Target Sudah di Tengah)
* Sudut hadap robot sudah lurus dengan target.
* ESP32 membaca sensor jarak fisik di bodi robot ($D$ dalam cm/meter):
  * **Jika $D > 120\text{ cm}$ (Target menjauh)**: Kedua motor bergerak **MAJU** mendekati target.
  * **Jika $80\text{ cm} \le D \le 120\text{ cm}$ (Jarak ideal tercapai)**: Kedua motor **BERHENTI** (*Hold Distance*).
  * **Jika $D < 80\text{ cm}$ (Target terlalu dekat)**: Kedua motor **MUNDUR** perlahan demi keselamatan.
  * **Jika $D < 30\text{ cm}$ (Batas Bahaya/Obstacle Terlalu Dekat)**: Pengereman darurat seketika (*Emergency Brake*).

### D. Fitur Keamanan: Serial Watchdog Timer
* Jika dalam waktu $> 500\text{ ms}$ ESP32 tidak menerima karakter data baru dari Raspberry Pi (misalnya kabel serial terlepas atau aplikasi Pi berhenti):
  * ESP32 otomatis mematikan semua motor demi keamanan.

---

## 6. Kesimpulan & Keuntungan Revisi

1. **Sangat Mudah Didebug**: Komunikasi serial dapat dimonitor langsung menggunakan Serial Monitor / terminal dengan membaca karakter sederhana (`-`, `x`, `+`, `s`).
2. **Tahan Banting & Andal**: Mengeliminasi risiko kesalahan parsing data float/string kompleks via serial.
3. **Pemisahan Kerja Seimbang**: Pi 5 murni mengolah Computer Vision; ESP32 murni mengolah sensor jarak hardware dan PID motor kecepatan tinggi.

