#include <Arduino.h>

void setup() {
  // Inisialisasi komunikasi serial dengan baud rate 115200
  Serial.begin(115200);
}

void loop() {
  // Cek apakah ada kiriman karakter dari Raspberry Pi
  if (Serial.available() > 0) {
    char cmd = Serial.read();  // Baca karakter '-', 'x', '+', atau 's'

    // Kirim konfirmasi balik ke Raspberry Pi
    Serial.print("ESP32 Menerima: ");
    Serial.println(cmd);

    // Respon gerakan motor / LED
    if (cmd == 'x') {
      // TARGET CENTER: Maju / Jaga Jarak
    } else if (cmd == '-') {
      // TARGET KIRI: Belok Kiri
    } else if (cmd == '+') {
      // TARGET KANAN: Belok Kanan
    } else if (cmd == 's') {
      // STOP: Matikan Motor
    }
  }
}