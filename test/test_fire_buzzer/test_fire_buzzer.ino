// TEST FIRE SENSOR + BUZZER/ALERT OUTPUTS - PBL5 ESP32
// Fire sensor DO -> GPIO33
// Buzzer         -> GPIO4
// Alert CH1      -> GPIO32
// Alert CH2      -> GPIO25
// Current firmware assumes fire sensor is ACTIVE LOW.

#define FIRE_SENSOR_PIN 33
#define BUZZER_PIN      4
#define ALERT_CH1_PIN   32
#define ALERT_CH2_PIN   25

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(FIRE_SENSOR_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(ALERT_CH1_PIN, OUTPUT);
  pinMode(ALERT_CH2_PIN, OUTPUT);

  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(ALERT_CH1_PIN, LOW);
  digitalWrite(ALERT_CH2_PIN, LOW);

  Serial.println("=== TEST FIRE SENSOR + BUZZER ===");
  Serial.println("Expected: LOW = FIRE, HIGH = normal");
}

void loop() {
  int fireVal = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireVal == LOW);

  Serial.print("FIRE_SENSOR=");
  Serial.println(fireDetected ? "LOW/FIRE" : "HIGH/NORMAL");

  digitalWrite(BUZZER_PIN, fireDetected ? HIGH : LOW);
  digitalWrite(ALERT_CH1_PIN, fireDetected ? HIGH : LOW);
  digitalWrite(ALERT_CH2_PIN, fireDetected ? HIGH : LOW);

  delay(300);
}
