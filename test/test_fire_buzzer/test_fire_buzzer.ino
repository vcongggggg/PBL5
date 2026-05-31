// TEST FIRE SENSOR + BUZZER - PBL5 ESP32
// Fire sensor DO -> GPIO33
// Buzzer         -> GPIO32
// Current firmware assumes fire sensor is ACTIVE LOW.

#define FIRE_SENSOR_PIN 33
#define BUZZER_PIN      32

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FIRE_SENSOR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("=== TEST FIRE SENSOR + BUZZER ===");
  Serial.println("Expected: LOW = FIRE, HIGH = normal");
}

void loop() {
  int fireVal = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireVal == LOW);

  Serial.print("FIRE_SENSOR=");
  Serial.println(fireDetected ? "LOW/FIRE" : "HIGH/NORMAL");

  digitalWrite(BUZZER_PIN, fireDetected ? HIGH : LOW);

  delay(300);
}
