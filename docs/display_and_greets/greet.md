# Spesifikasi Dialog Suara Resmi NEXUS (*NEXUS Voice Greets*)
============================================================

**Dokumen Versi**: 1.0  
**Tanggal**: 2026-09-08  
**Referensi**: `docs/1_concept/general_concept.md` (Bagian 8, 27, 28)  
**Target Modul**: `raspberry_pi/ui/speech_manager.py` & Audio Subsystem  

---

> [!IMPORTANT]
> ### 🎙️ Catatan Penting: Karakteristik Suara JARVIS
> Seluruh naskah dialog suara robot NEXUS dirancang untuk menggunakan **karakter suara JARVIS** (Iron Man AI):
> - **Aksen**: British English (Received Pronunciation / Oxford English yang halus).
> - **Tone / Karakter**: Tenang, percaya diri, sopan, berwibawa, dan futuristik khas asisten AI pribadi (*butler AI*).
> - **Penyampaian**: Artikulasi jelas, tempo bicara sedang (tidak terburu-buru), dan volume stabil.
> - **Format Aset**: File audio kualitas tinggi pre-rendered (`.wav` 16-bit 44.1 kHz / 24 kHz) agar dapat diputar instan tanpa latensi dan tanpa membebani prosesor Raspberry Pi.

---

## 1. Tabel Dialog Suara Resmi NEXUS

| No | Pemicu (*Event / State*) | Naskah Suara (*NEXUS Speech*) | Arti & Perilaku Robot |
| :---: | :--- | :--- | :--- |
| **1** | **Orang Terdeteksi Dekat (*Standby*)** | **“Welcome to the Technology and Information Department of Brawijaya University! Hello! I’m NEXUS. I’m ready to follow you. Please show me the password.”** | *Startup Greeting*: Menyapa pengunjung/dosen yang mendekati robot dan memberitahukan instruksi untuk menunjukkan gestur Victory Sign ✌️. *(Hanya dibunyikan 1 kali, dilengkapi cooldown agar tidak berulang).* |
| **2** | **Password Diterima (*Activation*)** | **“Hello! Nice to see you.”** | Diucapkan tepat saat gestur Victory Sign ✌️ terverifikasi dan robot beralih ke `NEXUS ON`. |
| **3** | **Target Terkunci (*Target Locked*)** | **“I’ll follow you.”** | Target ID orang terkunci dan sistem kendali motor mulai aktif membuntuti. |
| **4** | **Sedang Mengikuti (*Following Normally*)** | **“I’m right behind you.”** | Diucapkan secara berkala (*periodic check-in*) dengan jeda waktu panjang (misal tiap 30-60 detik) agar target merasa aman. |
| **5** | **Target Hilang Sementara (*Target Lost*)** | **“Where are you?”** | Diucapkan saat target keluar dari bidang pandang kamera *(robot berhenti dan masuk masa tenggang re-akuisisi 3.0 detik)*. |
| **6** | **Target Hilang Timeout $\to$ OFF** | **“I can’t find you.”** | Diucapkan setelah 3.0 detik target tidak kembali. Robot melepaskan kunci target dan otomatis mati kembali ke `NEXUS OFF`. |
| **7** | **Dimatikan oleh Target (*Deactivation*)** | **“Okay! See you later!”** | Diucapkan saat orang yang sedang diikuti menunjukkan gestur Victory Sign ✌️ untuk mematikan robot secara sengaja. |
| **8** | **Terjadi Gangguan Sistem (*System Error*)** | **“Something went wrong.”** | Peringatan keselamatan jika kamera terputus, serial UART gagal, atau baterai berada di batas kritis. |

---

## 2. Diagram Alur Suara dalam Siklus Operasi

```text
               ┌───────────────────────────────┐
               │     NEXUS STANDBY / OFF       │
               └───────────────┬───────────────┘
                               │
            (Ada orang mendekat dalam jangkauan)
                               │
                               ▼
               ┌───────────────────────────────┐
               │    1. STARTUP GREETING        │
               │  "Welcome to the Technology   │
               │   and Information Department  │
               │   of Brawijaya University!    │
               │   Hello! I’m NEXUS..."        │
               └───────────────┬───────────────┘
                               │
             (Target menunjukkan gestur Victory Sign ✌️)
                               │
                               ▼
               ┌───────────────────────────────┐
               │      2. ACTIVATION            │
               │  "Hello! Nice to see you."    │
               └───────────────┬───────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │     3. TARGET LOCKED          │
               │  "I’ll follow you."           │
               └───────────────┬───────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │    4. FOLLOWING NORMALLY      │ ◄───┐
               │  "I’m right behind you."      │     │
               └───────────────┬───────────────┘     │
                               │                     │
                    (Target hilang sejenak)          │ (Target kembali
                               │                      │  sebelum 3 detik)
                               ▼                     │
               ┌───────────────────────────────┐     │
               │     5. TARGET LOST            │     │
               │  "Where are you?"             │─────┘
               └───────────────┬───────────────┘
                               │
                 (Lewat dari batas 3.0 detik)
                               │
                               ▼
               ┌───────────────────────────────┐
               │   6. TARGET LOST TIMEOUT      │
               │  "I can’t find you."          │
               └───────────────┬───────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │       KEMBALI KE OFF          │
               └───────────────────────────────┘
```

---

## 3. Ketentuan Teknis Implementasi Suara

1. **Pemutaran Non-Blocking (Asynchronous)**:
   - Pemutaran file suara **tidak boleh menghentikan (*block*)** loop kamera atau pelacakan target.
   - Menggunakan *background thread* atau library seperti `pygame.mixer` / `aplay` secara non-blocking.
2. **Prioritas Suara**:
   - Jika robot beralih ke `NEXUS OFF` (misal deactivation atau target lost), suara deactivation boleh menginterupsi suara yang sedang berjalan.
3. **Mekanisme Cooldown**:
   - *Startup Greeting* memiliki cooldown (misal 15–30 detik) agar robot tidak menyapa berulang kali saat orang yang sama sedang berdiri di depan robot membaca poster/tampilan.
4. **Sinkronisasi dengan HMI / Display Layar**:
   - Setiap dialog suara disinkronkan dengan ekspresi animasi mata pada monitor fisik robot (misal ekspresi tersenyum saat *"Hello! Nice to see you."*, ekspresi mata mencari saat *"Where are you?"*).

