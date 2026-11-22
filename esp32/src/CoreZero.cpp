#include "main.h"

void ToFSensorRead() {
  if (vl53.dataReady()) {
    uint16_t distance;
    distance = vl53.distance();
    Serial.println(distance);
    if (distance == -1) {
      // something went wrong!
      Serial.print(F("Couldn't get distance: "));
      Serial.println(vl53.vl_status);
      state = false;
      return;
    }
    else {
      if(distance < Y_MIN_LIMIT) Forward_PID.now_value = 0;
      else Forward_PID.now_value = distance;
      Forward = PIDController(&Forward_PID);
      state = true;
    }
    // data is read out, time for another reading!
    vl53.clearInterrupt();
  }
}

void SerialRead(char* SerialInput) {
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
    if(Rotation_PID.now_value < X_MIN_LIMIT && Rotation_PID.now_value > -X_MIN_LIMIT) Rotation_PID.now_value = 0;
    Rotate = PIDController(&Rotation_PID);
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

  // Serial.printf("%d %f %f %f \n", delta_time, proportional, integral, derivative);

  return (proportional + integral + derivative);
}