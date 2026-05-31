// TEST ONLY 2 SERVOS - PBL5 ESP32
// Servo IN signal  -> GPIO14
// Servo OUT signal -> GPIO13
// IMPORTANT: Servo VCC uses external 5V supply, ESP32 GND and servo GND must be common.

#include <ESP32Servo.h>

#define SERVO_IN_PIN  14
#define SERVO_OUT_PIN 13

Servo servoIn;
Servo servoOut;

void setup() {
  Serial.begin(115200);
  delay(1000);

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);

  servoIn.setPeriodHertz(50);
  servoOut.setPeriodHertz(50);
  servoIn.attach(SERVO_IN_PIN, 500, 2400);
  servoOut.attach(SERVO_OUT_PIN, 500, 2400);

  Serial.println("=== TEST ONLY SERVOS ===");
}

void loop() {
  Serial.println("Close: 0 deg");
  servoIn.write(0);
  servoOut.write(0);
  delay(1500);

  Serial.println("Open: 80 deg");
  servoIn.write(80);
  servoOut.write(80);
  delay(1500);
}
