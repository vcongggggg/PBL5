#include <Arduino.h>
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
  // No relay/alert light is used in the current hardware.
  // Fire alarm sound is handled by buzzer_service on BUZZER_PIN.
  (void)on;
}

void handleAutoClose(bool fireAlertActive) {
  if (fireAlertActive) {
    return;
  }
  unsigned long now = millis();
  if (gateInOpen && (now - gateInOpenedAt > AUTO_CLOSE_MS)) {
    if (digitalRead(IR_IN_PIN) == LOW) {
      gateInOpenedAt = now; // Delay auto-close
      Serial.println("Gate IN auto-close deferred: IR_IN blocked");
    } else {
      closeGateIn();
    }
  }
  if (gateOutOpen && (now - gateOutOpenedAt > AUTO_CLOSE_MS)) {
    if (digitalRead(IR_OUT_PIN) == LOW) {
      gateOutOpenedAt = now; // Delay auto-close
      Serial.println("Gate OUT auto-close deferred: IR_OUT blocked");
    } else {
      closeGateOut();
    }
  }
}

