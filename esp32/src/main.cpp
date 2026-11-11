#include "main.h"

Adafruit_VL53L1X vl53 = Adafruit_VL53L1X(XSHUT_PIN, IRQ_PIN);
Adafruit_NeoPixel pixels(NUMPIXELS, WS2812PIN, NEO_GRB + NEO_KHZ800);
struct PIDDefaultdata Forward_PID ;
struct PIDDefaultdata Rotation_PID;

bool state = false;
int leftmotorlastpwm = 0, rightmotorlastpwm = 0;

void PIDInitialize() {
  Forward_PID.Kp = 1;
  Forward_PID.Ki = 1;
  Forward_PID.Kd = 1;
  Forward_PID.past_value = 0;
  Forward_PID.now_value = 0;
  Forward_PID.past_time = 0;
  Forward_PID.integral_value = 1;
  Forward_PID.setpoin = 1000;
  Forward_PID.integral_max_value = 1000;

  Rotation_PID.Kp = 1000;
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
  if(Serial.available() > 0) {
    uint8_t bytesRead = Serial.readBytesUntil('\n', SerialInput, 10);
    while(Serial.available() > 0) Serial.read();

    SerialInput[bytesRead] = '\0';

    uint8_t startpointer = 0;
    if(SerialInput[0] == 'X') {
      startpointer++;
      state = false;
    }
    else if(SerialInput[0] == 't') testscanner(SerialInput);
    else {
      state = true;
    }
    Rotation_PID.now_value = 0;
    int8_t multiplier = 1;
    bool decimalPointEncountered = false;
    int16_t decimalPlaces = 1;
    for(uint8_t chartoint = startpointer;;chartoint++) {
      if(SerialInput[chartoint] == '.') {
        decimalPointEncountered = true;
        continue;
      }
      if(SerialInput[chartoint] == '-') {
        multiplier *= -1;
        continue;
      }
      else if(SerialInput[chartoint] == '\0' || 
        SerialInput[chartoint] == '\r' || 
        SerialInput[chartoint] == '\n' || 
        SerialInput[chartoint] == ' ') {
        break; 
      }
      if(decimalPointEncountered) {
        decimalPlaces *= 10;
      }
      Rotation_PID.now_value *= 10;
      Rotation_PID.now_value += (int)(SerialInput[chartoint] - '0');
    }
    Rotation_PID.now_value *= multiplier;
    Rotation_PID.now_value /= decimalPlaces;
    Serial.printf("Rotation_PID.now_value: %f\n", Rotation_PID.now_value);
    if(Rotation_PID.now_value < X_MIN_LIMIT && Rotation_PID.now_value > -X_MIN_LIMIT) Rotation_PID.now_value = 0;
    ConditionalAdderControl();
  }
  // ToFSensorRead();
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

void ToFSensorRead() {
  if (vl53.dataReady()) {
    uint16_t distance;
    distance = vl53.distance();
    Serial.println(distance);
    if (distance == -1) {
      // something went wrong!
      Serial.print(F("Couldn't get distance: "));
      Serial.println(vl53.vl_status);
      return;
    }
    else {
      if(distance < Y_MIN_LIMIT) Forward_PID.now_value = 0;
      else Forward_PID.now_value = distance;
    }
    // data is read out, time for another reading!
    vl53.clearInterrupt();
  }
}

void ConditionalAdderControl() {
  //float Forward = PIDController(&Forward_PID);
  float Rotate = PIDController(&Rotation_PID);

  int LeftMotor = constrain(0 - (int)Rotate, -PWM_MAX_VAL, PWM_MAX_VAL);
  int RightMotor = constrain(0 + (int)Rotate, -PWM_MAX_VAL, PWM_MAX_VAL);

  Serial.printf("%d %d \n", LeftMotor, RightMotor);

  if(state) {
    if(LeftMotor > leftmotorlastpwm) {
      MotorRampUp(leftmotorlastpwm, LeftMotor, LEFT_MOTOR_CHAN);
    }
    else if(LeftMotor < leftmotorlastpwm) {
      MotorRampDown(leftmotorlastpwm, LeftMotor, LEFT_MOTOR_CHAN);
    }
    if(RightMotor > rightmotorlastpwm) {
      MotorRampUp(rightmotorlastpwm, RightMotor, RIGHT_MOTOR_CHAN);
    }
    else if(RightMotor < rightmotorlastpwm) {
      MotorRampDown(rightmotorlastpwm, RightMotor, RIGHT_MOTOR_CHAN);
    }
    leftmotorlastpwm = LeftMotor;
    rightmotorlastpwm = RightMotor;
  }
  else {
    ledcWrite(LEFT_MOTOR_CHAN, 0);
    ledcWrite(RIGHT_MOTOR_CHAN, 0);
  }
}

void MotorRampUp(int lastpwm, int targetpwm, uint8_t motorchannel) {
  for(int pwm = lastpwm; pwm <= targetpwm; pwm++) {
    ledcWrite(motorchannel, abs(pwm));
    delay(1);
    digitalWrite(motorchannel == LEFT_MOTOR_CHAN ? LEFTMOTORRELAYPIN : RIGHTMOTORRELAYPIN, pwm < 0 ? HIGH : LOW);
  }
}

void MotorRampDown(int lastpwm, int targetpwm, uint8_t motorchannel) {
  for(int pwm = lastpwm; pwm >= targetpwm; pwm--) {
    ledcWrite(motorchannel, abs(pwm));
    delay(1);
    digitalWrite(motorchannel == LEFT_MOTOR_CHAN ? LEFTMOTORRELAYPIN : RIGHTMOTORRELAYPIN, pwm < 0 ? HIGH : LOW);
  }
}

float PIDController(PIDDefaultdata* n) {
  unsigned long now_time = millis();
  unsigned int delta_time = now_time - n->past_time;
  float error = n->setpoin - n->now_value;
  float proportional, integral, derivative;

  n->past_time = now_time;

  proportional = error * n->Kp;

  n->integral_value += error;
  if(n->integral_value > n->integral_max_value) n->integral_value = n->integral_max_value;
  else if(n->integral_value < -n->integral_max_value) n->integral_value = -n->integral_max_value;
  
  integral = n->integral_value * n->Ki;

  derivative = ((error - n->past_value) / delta_time) * n->Kd;

  Serial.printf("%d %f %f %f \n", delta_time, proportional, integral, derivative);

  return (proportional + integral + derivative);
}