#include <Wire.h>
#include <VL53L1X.h>

VL53L1X sensor;

// Sesuaikan pin I2C default ESP32-S3 Anda
#define I2C_SDA 4
#define I2C_SCL 5

void setup() {
  Serial.begin(115200);
  
  // Memulai I2C dengan pin khusus ESP32-S3
  Wire.begin(I2C_SDA, I2C_SCL); 
  Wire.setClock(400000); // Mengatur I2C ke kecepatan tinggi (400 kHz)

  sensor.setTimeout(500);
  
  // Inisialisasi sensor
  if (!sensor.init()) {
    Serial.println("Gagal mendeteksi dan menginisialisasi sensor VL53L1X!");
    while (1); // Berhenti di sini jika gagal
  }

  // Pengaturan sensor
  // Gunakan VL53L1X::Short untuk jarak < 1.3m (lebih stabil terhadap cahaya)
  sensor.setDistanceMode(VL53L1X::Long);
  
  // Waktu ukur dalam mikrodetik (semakin besar semakin akurat, tapi lebih lambat)
  sensor.setMeasurementTimingBudget(50000); 

  // Mulai pengukuran kontinu tiap 50 milidetik
  sensor.startContinuous(50);
  
  Serial.println("Sensor siap!");
}

void loop() {
  // Membaca jarak dari sensor dalam milimeter
  uint16_t distance_mm = sensor.read();

  // Mengubah milimeter ke sentimeter
  float distance_cm = distance_mm / 10.0;

  Serial.print("Jarak: ");
  Serial.print(distance_cm);
  Serial.println(" cm");

  if (sensor.timeoutOccurred()) {
    Serial.println(" TIMEOUT (Sensor tidak merespons)");
  }

  delay(100);
}