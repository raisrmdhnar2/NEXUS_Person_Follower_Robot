#include <Wire.h>

void setup() {
  Serial.begin(115200);
  
  // Inisialisasi I2C di pin 8 (SDA) dan 9 (SCL)
  Wire.begin(8, 9);
  
  delay(2000); // Tunggu Serial siap
  Serial.println("\n--- Memulai I2C Scanner ---");
}

void loop() {
  byte error, address;
  int nDevices = 0;

  Serial.println("Scanning bus I2C...");

  for(address = 1; address < 127; address++ ) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("Alat I2C DITEMUKAN pada alamat 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
      nDevices++;
    }
    else if (error == 4) {
      Serial.print("Error tak dikenal pada alamat 0x");
      if (address < 16) {
        Serial.print("0");
      }
      Serial.println(address, HEX);
    }
  }
  
  if (nDevices == 0) {
    Serial.println("TIDAK ADA alat I2C yang terdeteksi.\n");
  } else {
    Serial.println("Scan selesai.\n");
  }

  delay(5000); // Ulangi setiap 5 detik
}
