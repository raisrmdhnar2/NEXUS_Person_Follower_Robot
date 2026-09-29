// Variabel untuk menyimpan data dari Raspberry Pi
char robot_cmd = 's';
float robot_dx = 0.0;

void setup() {
  // Inisialisasi komunikasi Serial dengan Raspberry Pi (115200 bps)
  Serial.begin(115200);
  
  // Tunggu sebentar agar serial stabil
  delay(100);
  Serial.println("\n[ESP32] Sistem Reset.");
  Serial.println("[ESP32] Menunggu data [cmd],[dx] dari Raspberry Pi...");
}

void loop() {
  // Cek apakah ada data serial yang masuk dari Raspberry Pi
  if (Serial.available() > 0) {
    
    // Baca data sampai karakter newline (\n)
    // Contoh format yang dikirim Raspi: "s,+0.00\n" atau "+,-0.25\n"
    String incomingData = Serial.readStringUntil('\n');
    
    // Cari posisi tanda koma
    int commaIndex = incomingData.indexOf(',');
    
    // Jika formatnya benar (ditemukan koma)
    if (commaIndex != -1) {
      // Parse karakter pertama sebagai command ('s', 'x', '+', '-')
      robot_cmd = incomingData.charAt(0);
      
      // Parse sisanya (setelah koma) sebagai nilai float (dx)
      String dxString = incomingData.substring(commaIndex + 1);
      robot_dx = dxString.toFloat();
      
      // -- DEBUG: Tampilkan kembali hasilnya ke Serial Monitor --
      Serial.print("Data Diterima -> Command: ");
      Serial.print(robot_cmd);
      Serial.print(" | Nilai dx: ");
      Serial.println(robot_dx, 4); // Print dengan 4 angka di belakang koma untuk akurasi
      
    } else {
      // Jika format yang diterima tidak sesuai ekspektasi
      Serial.print("Format salah! Data diterima: ");
      Serial.println(incomingData);
    }
  }
}
