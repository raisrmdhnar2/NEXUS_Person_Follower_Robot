#include <Arduino.h>

/**
 * ==============================================================================
 * NEXUS Person Follower Robot — ESP32 Motor Firmware (UART Packet Receiver)
 * ==============================================================================
 * Menerima paket serial berformat: "[Perintah],[dx]\n"
 * Contoh:
 *   - "s,+0.00\n" -> STOP (Robot OFF / Target Hilang)
 *   - "x,+0.02\n" -> TARGET CENTER (Maju lurus / Jaga jarak dengan sensor)
 *   - "-,-0.35\n" -> TARGET KIRI (Belok kiri proporsional sebanding |dx|)
 *   - "+,+0.60\n" -> TARGET KANAN (Belok kanan proporsional sebanding |dx|)
 * ==============================================================================
 */

// Konfigurasi kecepatan motor dasar (sesuaikan dengan driver & motor robot Anda)
const int BASE_SPEED = 150;     // PWM dasar maju (0 - 255)
const float TURN_GAIN = 100.0;  // Faktor pengali Kp kemudi proporsional

// Variabel status kendali
char current_cmd = 's';
float current_dx = 0.0;
unsigned long last_packet_time = 0;
const unsigned long WATCHDOG_TIMEOUT_MS = 500;  // Auto-stop jika serial terputus > 500ms

void stopMotors() {
  // TODO: Matikan PWM kedua motor (PWM = 0)
  // analogWrite(PIN_MOTOR_L, 0);
  // analogWrite(PIN_MOTOR_R, 0);
}

void driveMotors(int speedLeft, int speedRight) {
  // Batasi nilai PWM antara 0 hingga 255
  speedLeft = constrain(speedLeft, 0, 255);
  speedRight = constrain(speedRight, 0, 255);

  // TODO: Tulis ke pin driver motor (misal: L298N, TB6612, atau BTS7960)
  // analogWrite(PIN_MOTOR_L, speedLeft);
  // analogWrite(PIN_MOTOR_R, speedRight);
}

void setup() {
  // Inisialisasi komunikasi serial UART dengan baud rate 115200 bps
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }
  Serial.println("[ESP32] NEXUS Motor Controller Initialized.");
  stopMotors();
}

void loop() {
  // 1. Cek apakah ada data serial masuk dari Raspberry Pi
  if (Serial.available() > 0) {
    // Baca satu baris utuh hingga karakter delimiter newline '\n'
    String packet = Serial.readStringUntil('\n');
    packet.trim();  // Hapus karakter whitespace atau '\r'

    if (packet.length() > 0) {
      last_packet_time = millis();  // Reset watchdog timer
      
      // Ambil karakter perintah utama di awal string
      current_cmd = packet.charAt(0);
      current_dx = 0.0;

      // Cari pemisah koma ',' untuk mengekstrak nilai float dx
      int commaIndex = packet.indexOf(',');
      if (commaIndex != -1 && commaIndex + 1 < (int)packet.length()) {
        current_dx = packet.substring(commaIndex + 1).toFloat();
      }

      // Cetak debug kembali ke Raspberry Pi / Serial Monitor
      Serial.print("ESP32 Menerima -> Cmd: '");
      Serial.print(current_cmd);
      Serial.print("', dx: ");
      Serial.println(current_dx, 2);

      // 2. Eksekusi Gerakan Motor
      if (current_cmd == 's') {
        // [STOP]: NEXUS OFF, Target belum terkunci, atau Target hilang
        stopMotors();
      } 
      else if (current_cmd == 'x') {
        // [TARGET CENTER]: Target lurus di depan
        // ESP32 dapat maju lurus sambil membaca sensor jarak fisik (ToF / Ultrasonik)
        driveMotors(BASE_SPEED, BASE_SPEED);
      } 
      else if (current_cmd == '-') {
        // [BELOK KIRI]: dx bernilai negatif (misal -0.45)
        // Roda kanan bergerak lebih cepat, roda kiri melambat sebanding nilai |dx|
        float turn_effort = abs(current_dx) * TURN_GAIN;
        int speedLeft = (int)(BASE_SPEED - turn_effort);
        int speedRight = (int)(BASE_SPEED + turn_effort);
        driveMotors(speedLeft, speedRight);
      } 
      else if (current_cmd == '+') {
        // [BELOK KANAN]: dx bernilai positif (misal +0.45)
        // Roda kiri bergerak lebih cepat, roda kanan melambat sebanding nilai dx
        float turn_effort = current_dx * TURN_GAIN;
        int speedLeft = (int)(BASE_SPEED + turn_effort);
        int speedRight = (int)(BASE_SPEED - turn_effort);
        driveMotors(speedLeft, speedRight);
      }
    }
  }

  // 3. Safety Watchdog: Jika kabel serial terputus atau Pi hang > 500ms, matikan motor
  if (millis() - last_packet_time > WATCHDOG_TIMEOUT_MS && current_cmd != 's') {
    current_cmd = 's';
    stopMotors();
    Serial.println("[ESP32] ⚠️ Watchdog Timeout! Serial connection lost -> Motors STOPPED.");
  }
}