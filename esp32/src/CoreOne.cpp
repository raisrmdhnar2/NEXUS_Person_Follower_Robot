#include "main.h"

void MotorDriver(void *pvParameters) {
    int leftmotorlastpwm = 0, rightmotorlastpwm = 0;
    for(;;) {
        int LeftMotor = constrain((int)Forward - (int)Rotate, -PWM_MAX_VAL, PWM_MAX_VAL);
        int RightMotor = constrain((int)Forward + (int)Rotate, -PWM_MAX_VAL, PWM_MAX_VAL);

        Serial.printf("Left Motor: %d, Right Motor: %d, Forward: %f, Rotate: %f State: %s \n", LeftMotor, RightMotor, Forward, Rotate, state ? "true" : "false");

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
        vTaskDelay(10 / portTICK_PERIOD_MS);
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