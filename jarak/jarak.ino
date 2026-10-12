#include <Wire.h>
#include "Adafruit_VL53L1X.h"

// Sesuaikan pin I2C default ESP32-S3 Anda
#define I2C_SDA 8
#define I2C_SCL 9

// Pin XSHUT dan IRQ (Set ke -1 jika Anda tidak menghubungkannya ke ESP32)
#define IRQ_PIN -1
#define XSHUT_PIN -1

Adafruit_VL53L1X vl53 = Adafruit_VL53L1X(XSHUT_PIN, IRQ_PIN);

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println(F("Adafruit VL53L1X sensor demo"));

  // Memulai I2C dengan pin khusus ESP32-S3 Anda
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(400000); // Mengatur I2C ke kecepatan tinggi (400 kHz)

  // Inisialisasi sensor
  if (! vl53.begin(0x29, &Wire)) {
    Serial.print(F("Error on init of VL sensor: "));
    Serial.println(vl53.vl_status);
    while (1) delay(10);
  }
  Serial.println(F("VL53L1X sensor OK!"));

  Serial.print(F("Sensor ID: 0x"));
  Serial.println(vl53.sensorID(), HEX);

  // Mulai pengukuran
  if (! vl53.startRanging()) {
    Serial.print(F("Couldn't start ranging: "));
    Serial.println(vl53.vl_status);
    while (1) delay(10);
  }
  Serial.println(F("Ranging started"));

  // Valid timing budgets: 15, 20, 33, 50, 100, 200 and 500ms!
  vl53.setTimingBudget(50);
  Serial.print(F("Timing budget (ms): "));
  Serial.println(vl53.getTimingBudget());
}

void loop() {
  int16_t distance_mm;

  // Cek apakah ada data baru dari sensor
  if (vl53.dataReady()) {
    
    distance_mm = vl53.distance(); // Membaca jarak dalam milimeter
    
    if (distance_mm == -1) {
      // Terjadi kesalahan pembacaan
      Serial.print(F("Couldn't get distance: "));
      Serial.println(vl53.vl_status);
      return;
    }

    // Mengubah milimeter ke sentimeter (sesuai kode Anda sebelumnya)
    float distance_cm = distance_mm / 10.0;

    Serial.print(F("Jarak: "));
    Serial.print(distance_cm);
    Serial.println(F(" cm"));

    // Wajib dipanggil! Memberitahu sensor untuk mengambil pembacaan berikutnya
    vl53.clearInterrupt();
  }
}