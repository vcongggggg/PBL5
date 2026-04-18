#include <ESP32Servo.h>

#include "config.h"
#include "gate_controller.h"

static Servo gateInServo;
static Servo gateOutServo;

static bool gateInOpen = false;
static bool gateOutOpen = false;
static unsigned long gateInOpenedAt = 0;
static unsigned long gateOutOpenedAt = 0;

void initGateHardware() {
  pinMode(RELAY_CH1_PIN, OUTPUT);
  pinMode(RELAY_CH2_PIN, OUTPUT);
  digitalWrite(RELAY_CH1_PIN, LOW);
  digitalWrite(RELAY_CH2_PIN, LOW);

  gateInServo.attach(SERVO_IN_PIN);
  gateOutServo.attach(SERVO_OUT_PIN);
  gateInServo.write(ANGLE_CLOSED);
  gateOutServo.write(ANGLE_CLOSED);
}

void openGateIn() {
  gateInServo.write(ANGLE_OPEN);
  gateInOpen = true;
  gateInOpenedAt = millis();
  Serial.println("Gate IN OPEN");
}

void closeGateIn() {
  gateInServo.write(ANGLE_CLOSED);
  gateInOpen = false;
  Serial.println("Gate IN CLOSED");
}

void openGateOut() {
  gateOutServo.write(ANGLE_OPEN);
  gateOutOpen = true;
  gateOutOpenedAt = millis();
  Serial.println("Gate OUT OPEN");
}

void closeGateOut() {
  gateOutServo.write(ANGLE_CLOSED);
  gateOutOpen = false;
  Serial.println("Gate OUT CLOSED");
}

void setAlertRelays(bool on) {
  digitalWrite(RELAY_CH1_PIN, on ? HIGH : LOW);
  digitalWrite(RELAY_CH2_PIN, on ? HIGH : LOW);
}

void handleAutoClose(bool fireAlertActive) {
  if (fireAlertActive) {
    return;
  }
  unsigned long now = millis();
  if (gateInOpen && (now - gateInOpenedAt > AUTO_CLOSE_MS)) {
    closeGateIn();
  }
  if (gateOutOpen && (now - gateOutOpenedAt > AUTO_CLOSE_MS)) {
    closeGateOut();
  }
}

