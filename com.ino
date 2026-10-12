// Status dan Data dari Raspberry Pi
bool robot_is_active = false;
float robot_dx = 0.0;

void setup() {
  // Inisialisasi komunikasi Serial dengan Raspberry Pi (115200 bps)
  Serial.begin(115200);
  delay(100);
  
  Serial.println("\n[ESP32] Sistem Siap.");
  Serial.println("[ESP32] Protokol: 'X' (Mati) | Nilai Float dx (Hidup)");
}

void loop() {
  // Cek apakah ada data serial dari Raspberry Pi
  if (Serial.available() > 0) {
    // Baca data sampai karakter newline (\n)
    String incomingData = Serial.readStringUntil('\n');
    incomingData.trim(); // Bersihkan karakter liar seperti \r atau spasi

    if (incomingData.length() == 0) return;

    // 1. Jika menerima "X" -> Robot MATI (Motor Berhenti)
    if (incomingData.equalsIgnoreCase("X")) {
      robot_is_active = false;
      robot_dx = 0.0;
      
      // Tampilkan ke Serial Monitor
      Serial.println("[Status: OFF] Motor Stop (X)");
    } 
    // 2. Jika menerima nilai float dx -> Robot HIDUP (Mengikuti Target)
    else {
      robot_is_active = true;
      robot_dx = incomingData.toFloat();
      
      // Tampilkan ke Serial Monitor
      Serial.print("[Status: ON] dx: ");
      Serial.println(robot_dx, 4);
    }
  }
}

