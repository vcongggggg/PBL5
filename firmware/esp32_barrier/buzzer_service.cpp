#include <Arduino.h>
#include "config.h"
#include "buzzer_service.h"

static bool fireAlarmActive = false;
static unsigned long lastToggle = 0;
static bool buzzerState = false;

void initBuzzer() {
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  Serial.println("[BUZZER] Initialized on GPIO " + String(BUZZER_PIN));
}

void buzzerBeep() {
  // Beep ngắn 100ms
  digitalWrite(BUZZER_PIN, HIGH);
  delay(100);
  digitalWrite(BUZZER_PIN, LOW);
}

void buzzerDoubleBeep() {
  // 2 tiếng beep ngắn
  digitalWrite(BUZZER_PIN, HIGH);
  delay(80);
  digitalWrite(BUZZER_PIN, LOW);
  delay(80);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(80);
  digitalWrite(BUZZER_PIN, LOW);
}

void buzzerLongBeep() {
  // Beep dài 500ms
  digitalWrite(BUZZER_PIN, HIGH);
  delay(500);
  digitalWrite(BUZZER_PIN, LOW);
}

void buzzerFireAlarm(bool on) {
  fireAlarmActive = on;
  if (!on) {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerState = false;
  }
}

void handleBuzzerLoop() {
  if (!fireAlarmActive) return;

  unsigned long now = millis();
  // Kêu liên tục: bật/tắt mỗi 300ms
  if (now - lastToggle > 300) {
    buzzerState = !buzzerState;
    digitalWrite(BUZZER_PIN, buzzerState ? HIGH : LOW);
    lastToggle = now;
  }
}
