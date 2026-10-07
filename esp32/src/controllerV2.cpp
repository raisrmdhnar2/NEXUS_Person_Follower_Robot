#include "main.h"

Adafruit_VL53L1X vl53 = Adafruit_VL53L1X(XSHUT_PIN, IRQ_PIN);
Adafruit_NeoPixel pixels(NUMPIXELS, WS2812PIN, NEO_GRB + NEO_KHZ800);
struct PIDDefaultdata PIDONE;

void setup() {
  Serial.begin(115200);
  Wire.begin(SDAPIN, SCLPIN);
  pinMode(LEFTMOTORPIN, OUTPUT);
  pinMode(RIGHTMOTORPIN, OUTPUT);

  ledcAttachPin(LEFTMOTORPIN, LEFT_MOTOR_CHAN);
  ledcAttachPin(RIGHTMOTORPIN, RIGHT_MOTOR_CHAN);

  ledcChangeFrequency(LEFT_MOTOR_CHAN, PWM_FREQ, PWM_RES);
  ledcChangeFrequency(RIGHT_MOTOR_CHAN, PWM_FREQ, PWM_RES);
  Initializing();
}

void loop() {
  int16_t distance;

  if (vl53.dataReady()) {
    // new measurement for the taking!
    distance = vl53.distance();
    if (distance == -1) {
      // something went wrong!
      Serial.print(F("Couldn't get distance: "));
      Serial.println(vl53.vl_status);
      return;
    }
    Serial.print(F("Distance: "));
    Serial.print(distance);
    Serial.println(" mm");

    // data is read out, time for another reading!
    vl53.clearInterrupt();
  }
}

void Initializing() {
  pixels.begin();

  pixels.clear();

  for(uint8_t n = 0; n < 256; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }
  for(uint8_t n = 255; n > 0; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }
  for(uint8_t n = 0; n < 256; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }
  for(uint8_t n = 0; n < 256; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }
  for(uint8_t n = 0; n < 256; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }
  for(uint8_t n = 0; n < 256; n++) {
    pixels.setPixelColor(0, pixels.Color(n, 0, 0));
    pixels.show();
    delay(200);
  }


  if (! vl53.begin(0x29, &Wire)) {
    Serial.print(F("Error on init of VL sensor: "));
    Serial.println(vl53.vl_status);
    while(1) delay(10);
  }
  if (! vl53.startRanging()) {
    Serial.print(F("Couldn't start ranging: "));
    Serial.println(vl53.vl_status);
    while(1) delay(10);
  }
  vl53.setTimingBudget(50);
  Serial.print(F("Timing budget (ms): "));
  Serial.println(vl53.getTimingBudget());
}

float PIDController(PIDDefaultdata* n) {
  unsigned long now_time = millis();
  unsigned int delta_time = now_time - n->past_time;
  float error = n->setpoin - n->now_value;
  float proportional, integral, derivative;

  n->past_time = now_time;

  proportional = error * n->Kp;

  n->integral_value += error;
  integral = n->integral_value * n->Ki;

  derivative = ((error - n->past_value) / delta_time) * n->Kd;

  return (proportional + integral + derivative);
}
