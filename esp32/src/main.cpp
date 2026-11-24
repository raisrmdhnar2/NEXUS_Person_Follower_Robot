#include "main.h"

Adafruit_VL53L1X vl53 = Adafruit_VL53L1X(XSHUT_PIN, IRQ_PIN);
Adafruit_NeoPixel pixels(NUMPIXELS, WS2812PIN, NEO_GRB + NEO_KHZ800);
struct PIDDefaultdata Forward_PID ;
struct PIDDefaultdata Rotation_PID;

SemaphoreHandle_t SerialMutex;
SemaphoreHandle_t VariableMutex;

bool state = false;
float Forward = 0, Rotate = 0;
unsigned long lastSerialRead = 0;

void PIDInitialize() {
  Forward_PID.Kp = 10;
  Forward_PID.Ki = 1;
  Forward_PID.Kd = 1;
  Forward_PID.past_value = 0;
  Forward_PID.now_value = 0;
  Forward_PID.past_time = 0;
  Forward_PID.integral_value = 1;
  Forward_PID.setpoin = 500;
  Forward_PID.integral_max_value = 1000;

  Rotation_PID.Kp = 300;
  Rotation_PID.Ki = 0;
  Rotation_PID.Kd = 0;
  Rotation_PID.past_value = 0;
  Rotation_PID.now_value = 0;
  Rotation_PID.past_time = 0;
  Rotation_PID.integral_value = 1;
  Rotation_PID.setpoin = 0;
  Rotation_PID.integral_max_value = 1000;
}

void setup() {
  Serial.begin(115200);
  // if(Wire.begin(SDAPIN, SCLPIN)) Serial.println("I2C Connected");
  // else{
  //   Serial.println("I2C Doesn't connect");
  // }

  SerialMutex = xSemaphoreCreateMutex();
  VariableMutex = xSemaphoreCreateMutex();
  pinMode(LEFTMOTORPWMPIN, OUTPUT);
  pinMode(RIGHTMOTORPWMPIN, OUTPUT);
  pinMode(RIGHTMOTORRELAYPIN, OUTPUT);
  pinMode(LEFTMOTORRELAYPIN, OUTPUT);

  ledcSetup(LEFT_MOTOR_CHAN, PWM_FREQ, PWM_RES);
  ledcSetup(RIGHT_MOTOR_CHAN, PWM_FREQ, PWM_RES);

  ledcAttachPin(LEFTMOTORPWMPIN, LEFT_MOTOR_CHAN);
  ledcAttachPin(RIGHTMOTORPWMPIN, RIGHT_MOTOR_CHAN);
  Initializing();
}

void loop() {
  char SerialInput[10] = "";
  if(xSemaphoreTake(VariableMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
    
    // ToFSensorRead();
    Forward = 0;
  
    if(xSemaphoreTake(SerialMutex, pdMS_TO_TICKS(100)) == pdTRUE) {
      if(Serial.available() > 0) {
        SerialRead(SerialInput);
        lastSerialRead = millis();
      }
      xSemaphoreGive(SerialMutex);
    }
  
      // if(millis() - lastSerialRead > 500) {
      //   state = false;
      // }
    xSemaphoreGive(VariableMutex);
  }
}

void Initializing() {
  pixels.begin();

  pixels.clear();

  for(uint8_t n = 0; n < 254; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(2);
  }
  for(uint8_t n = 255; n > 0; n--) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(2);
  }
  for(uint8_t n = 0; n < 254; n++) {
    pixels.setPixelColor(0, pixels.Color(0, n, 0));
    pixels.show();
    delay(2);
  }
  for(uint8_t n = 255; n > 0; n--) {
    pixels.setPixelColor(0, pixels.Color(0, n, 0));
    pixels.show();
    delay(2);
  }
  for(uint8_t n = 0; n < 254; n++) {
    pixels.setPixelColor(0, pixels.Color(0, 0, n));
    pixels.show();
    delay(2);
  }
  for(uint8_t n = 255; n > 0; n--) {
    pixels.setPixelColor(0, pixels.Color(0, 0, n));
    pixels.show();
    delay(2);
  }
  pixels.clear();

  xTaskCreatePinnedToCore(MotorDriver, "MotorDriver", 2048, NULL, 1, NULL, 0);

  // if (! vl53.begin(0x29, &Wire)) {
  //   Serial.print(F("Error on init of VL sensor: "));
  //   Serial.println(vl53.vl_status);
  //   while(1) delay(10);
  // }
  // if (! vl53.startRanging()) {
  //   Serial.print(F("Couldn't start ranging: "));
  //   Serial.println(vl53.vl_status);
  //   while(1) delay(10);
  // }
  // vl53.setTimingBudget(50);
  // Serial.print(F("Timing budget (ms): "));
  // Serial.println(vl53.getTimingBudget());

  PIDInitialize();
}
