# Dokumen Revisi Konsep: Kontrol Gerak & Komunikasi NEXUS
================================================================

**Dokumen Versi**: 2.0  
**Tanggal**: 2026-09-28  
**Status**: Disetujui (Approved)  
**Target Modul**: 
- Raspberry Pi 5 (`top_module.py`, `esp32_uart.py`)
- ESP32 Motor Firmware (`esp32/src/main/main.ino`)
- Hardware: TOF400C-VL53L1X, Motor PG36 24V 222 RPM, Driver BTS7960 (43A)

---

## 1. Latar Belakang & Motivasi Perubahan

Pada perancangan awal, komunikasi hanya menggunakan kode diskrit 1-byte (`'-'`, `'+'`, `'x'`, `'s'`). Pendekatan tersebut berhasil untuk uji coba awal, namun pergerakan robot terasa kaku/patah-patah saat berbelok (*bang-bang control*) karena ESP32 tidak mengetahui seberapa jauh target melenceng dari tengah kamera.

Untuk mencapai pergerakan roda yang **halus (*smooth*), proporsional, dan aman**, arsitektur sistem diperbarui menjadi **Hybrid Command & Proportional Kinematic Protocol**:
1. **Raspberry Pi 5**: Mengirimkan status perintah utama beserta nilai deviasi horizontal kontinu target:
   $$\text{Format: } \mathbf{[cmd],[dx]\backslash n}$$
2. **ESP32 (Dual Core FreeRTOS)**:
   - **Core 0 (I/O & Komunikasi)**: Membaca UART `(cmd, dx)`, membaca sensor jarak laser **TOF400C-VL53L1X** via I2C, serta mengakuisisi interrupt encoder motor.
   - **Core 1 (Real-Time Control Loop)**: Menjalankan pengereman darurat (*Safety Override* dengan Histeresis), kalkulasi kinematika diferensial, kontrol PID loop tertutup, dan kompensasi *deadband* girboks planetary **PG36**.
   - **Driver BTS7960 (43A)**: Mengeksekusi sinyal PWM dan proteksi pin Enable (`L_EN`, `R_EN`).

---

## 2. Pemisahan Tanggung Jawab (*Separation of Concerns*)

```
┌────────────────────────────────────────────────────────┐
│                   RASPBERRY PI 5                       │
│  - Image Acquisition & Camera Pipeline (640x480 @ 30fps)│
│  - YOLOv8 Person Detection                             │
│  - MediaPipe 3D Landmark Gesture (Victory ✌️ Password) │
│  - IoU Multi-Person Tracking & Target Locking          │
│  - 3.0s Auto-Loss Timeout & State Machine (ON/OFF)     │
│  - Continuous Target Deviation Calculator (dx)         │
│  - Steering Evaluator (dx -> cmd: '-', 'x', '+', 's')  │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │ UART Serial: "[cmd],[dx]\n"
                           │ Baudrate: 115200 bps (Rate Limit: ~25 Hz)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   ESP32 (FreeRTOS)                     │
│  [Core 0: Input Sensor & Komunikasi]                   │
│  - Parser UART Packet: cmd ('s','x','-','+') & dx      │
│  - Sensor Jarak Laser I2C: TOF400C-VL53L1X             │
│  - Encoder Ticks Reader (Quadrature Interrupts)        │
│                                                        │
│  [Core 1: Safety & Closed-Loop Control]                │
│  - Safety Override (Hysteresis <=50cm / >=65cm & 's')  │
│  - Differential Drive Kinematics (v, omega dari dx)    │
│  - Closed-Loop Speed PID (Error = Target - Actual)     │
│  - Motor PG36 Planetary Gearbox Deadband Compensation  │
│  - Dual BTS7960 H-Bridge PWM & Enable Generation       │
│  - Hardware Watchdog Timer (500 ms Auto-Stop)          │
└────────────────────────────────────────────────────────┘
```

---

## 3. Spesifikasi Protokol Serial UART (Pi $\to$ ESP32)

Komunikasi menggunakan jalur Serial UART dengan format teks ASCII berbatas koma dan diakhiri karakter *newline* (`\n`).

### Format Paket:
$$\mathbf{[cmd],[dx]\backslash n}$$

* **`[cmd]`** (1 karakter): Status perintah robot (`'s'`, `'x'`, `'-'`, `'+'`).
* **`,`** : Pemisah (*comma delimiter*).
* **`[dx]`** (Float berformat `+0.00` atau `-0.00`): Deviasi horizontal target ternormalisasi terhadap titik tengah kamera $[-1.0, +1.0]$.
* **`\n`** : Karakter penutup baris (*line feed / newline*).

### Tabel Status & Logika:

| Karakter `cmd` | Rentang `dx` | Kondisi di Raspberry Pi | Respon Motor di ESP32 |
| :---: | :---: | :--- | :--- |
| **`'s'`** | `+0.00` | Robot OFF, Standby, atau Target Hilang | **STOP Darurat**: `L_EN & R_EN = LOW`, PWM = 0, Reset Integral PID. |
| **`'x'`** | $[-0.15, +0.15]$ | Target berada di tengah (*Aligned*) | **Maju Lurus**: Kedua motor melaju, kecepatan $v$ diatur berbasis sensor TOF400C untuk menjaga jarak ideal (~80–120 cm). |
| **`'-'`** | $dx < -0.15$ | Target di sebelah kiri kamera | **Belok Kiri Halus**: $v_L = v - \Delta v$, $v_R = v + \Delta v$, di mana $\Delta v = |dx| \times K_{\text{turn}}$. |
| **`'+'`** | $dx > +0.15$ | Target di sebelah kanan kamera | **Belok Kanan Halus**: $v_L = v + \Delta v$, $v_R = v - \Delta v$, di mana $\Delta v = |dx| \times K_{\text{turn}}$. |

---

## 4. Logika di Sisi Raspberry Pi 5

Raspberry Pi mengevaluasi nilai penyimpangan horizontal target ($dx$) dari titik tengah frame:
$$\text{center\_x} = \frac{x_1 + x_2}{2}$$
$$dx = \frac{\text{center\_x} - \frac{W}{2}}{\frac{W}{2}} \quad \in [-1.0, +1.0]$$

### Konsep Deadzone (Toleransi Tengah)
Batas toleransi tengah (*deadzone*) tetap digunakan untuk menentukan simbol diskrit `cmd`:
$$\text{DEADZONE} = 0.15 \quad (\pm 15\% \text{ dari tengah layar})$$

Pengiriman data dieksekusi melalui metode `send_command(cmd, dx=target_dx)` pada [`Esp32UartBridge`](file:///home/nexus_is/NEXUS_Person_Follower_Robot/raspberry_pi/communication/esp32_uart.py).

---

## 5. Logika di Sisi ESP32 (Sesuai `docs/flowchart.png`)

Firmware ESP32 mengimplementasikan alur kendali berikut:

### A. Core 0: Input Sensor & Komunikasi
1. **UART Listener**: Membaca paket serial hingga `\n`, memisahkan `cmd` dan `dx`.
2. **Sensor TOF400C-VL53L1X**: Membaca jarak $D$ dalam cm/mm secara non-blocking via bus I2C.
3. **Interrupt Encoder**: Mengakuisisi pulsa *hall-effect* dari motor PG36 untuk menghitung kecepatan aktual per milidetik.

### B. Core 1: Logika Keselamatan & Rem (*Safety Override*)
Mencegah terjadinya benturan dengan target atau halangan di depan:
1. **Hysteresis Pengereman Darurat**:
   * Jika $D \le 50\text{ cm}$: Aktifkan `isEmergencyBrake = TRUE`.
   * Jika $D \ge 65\text{ cm}$: Lepaskan `isEmergencyBrake = FALSE`.
2. **Kondisi Target Hilang**:
   * Jika `cmd == 's'`: `isEmergencyBrake = TRUE`.
3. **Aksi Saat Rem Aktif**:
   * Matikan pin Enable driver BTS7960: `L_EN = LOW`, `R_EN = LOW`.
   * Nol-kan target kecepatan: $v_L = 0, v_R = 0$.
   * **Reset akumulasi integral PID (I-term)** untuk mencegah lonjakan torsi saat motor aktif kembali (*Anti-Windup*).

### C. Core 1: Kinematika Diferensial & Closed-Loop PID
Jika `isEmergencyBrake == FALSE`:
1. Aktifkan driver: `L_EN = HIGH`, `R_EN = HIGH`.
2. Hitung kecepatan linear $v$ (berdasarkan jarak TOF400C menuju setpoint ideal 90–100 cm).
3. Hitung kecepatan sudut: $\omega = K_{\text{turn}} \times dx$.
4. Konversi kinematika diferensial:
   $$v_L = v - \frac{\omega \cdot L}{2}, \quad v_R = v + \frac{\omega \cdot L}{2}$$
5. Hitung kontrol PID kecepatan motor per roda:
   $$u(t) = K_p \cdot e(t) + K_i \int e(t)\,dt + K_d \frac{de(t)}{dt}$$
6. **Kompensasi Deadband Motor PG36**:
   Karena girboks *planetary* PG36 24V memiliki hambatan gesek awal, ditambahkan offset tegangan minimum (misal $\pm 35$ PWM) pada nilai $u(t)$ yang bukan nol.
7. Petakan ke sinyal PWM (`RPWM` dan `LPWM`) untuk dikirim ke modul BTS7960.

### D. Fitur Keamanan: Hardware Watchdog Timer
Jika dalam kurun waktu $> 500\text{ ms}$ tidak ada paket data serial baru yang diterima dari Raspberry Pi:
* ESP32 otomatis memaksa `cmd = 's'` dan mengaktifkan rem darurat.

---

## 6. Kesimpulan & Keunggulan Revisi

1. **Pergerakan Roda Halus & Mulus**: Belok tidak lagi menyentak karena kecepatan diferensial roda kiri & kanan proporsional terhadap besaran deviasi $dx$.
2. **Respon Cepat & Aman**: Rem darurat berbasis laser ToF dan pemutus enable BTS7960 dieksekusi langsung di ESP32 dalam hitungan milidetik tanpa bergantung pada Raspberry Pi.
3. **Bebas Jitter & Efisien**: Pembagian beban Core 0 (I/O) dan Core 1 (PID) pada ESP32 menjamin frekuensi loop kendali tetap konstan dan stabil.
