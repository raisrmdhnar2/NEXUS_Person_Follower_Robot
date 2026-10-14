#pragma once

#include <Arduino.h>
#include "Adafruit_VL53L1X.h"
#include "Adafruit_NeoPixel.h"
#include "logging.h"

#define IRQ_PIN 10
#define XSHUT_PIN 11
#define SDAPIN 8
#define SCLPIN 9
#define LEFTMOTORRELAYPIN 1
#define LEFTMOTORPWMPIN 5
#define LEFT_MOTOR_CHAN 0
#define RIGHTMOTORRELAYPIN 4
#define RIGHTMOTORPWMPIN 6
#define RIGHT_MOTOR_CHAN 1
#define PWM_FREQ 500
#define PWM_RES 10
#define PWM_MAX_VAL 1023
#define INPUT_MAX_VALUE 10000
#define WS2812PIN 48
#define NUMPIXELS 1

struct PIDDefaultdata
{
    float Kp, Kd, Ki;
    float past_value, now_value, integral_value, setpoin;
    unsigned long past_time;
};

float PIDController(PIDDefaultdata* n);

void Initializing();

void PIDInitialize();

void ToFSensorRead();

void MotorDriver();

void ConditionalAdderControl();

void fadingLED(uint8_t startvalue, uint8_t endvalue, uint8_t colour);
