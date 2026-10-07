#pragma once

#include <Arduino.h>
#include "Adafruit_VL53L1X.h"
#include "Adafruit_NeoPixel.h"

#define IRQ_PIN 2
#define XSHUT_PIN 3
#define SDAPIN 8
#define SCLPIN 9
#define LEFTMOTORPIN 1
#define LEFT_MOTOR_CHAN 0
#define RIGHTMOTORPIN 4
#define RIGHT_MOTOR_CHAN 1
#define PWM_FREQ 100000
#define PWM_RES 16
#define PWM_MAX_VAL 222222
#define INPUT_MAX_VALUE 2817838
#define PWMtoVALRATIO 10
#define WS2812PIN 6
#define NUMPIXELS 16

struct PIDDefaultdata
{
    float Kp, Kd, Ki;
    float past_value, now_value, integral_value, setpoin;
    unsigned long past_time;
};

float PIDController(PIDDefaultdata* n);

void Initializing();

void fadingLED(uint8_t startvalue, uint8_t endvalue, uint8_t colour);
