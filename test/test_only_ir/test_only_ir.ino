// TEST ONLY IR SENSORS - PBL5 ESP32
// IR IN  OUT -> GPIO27
// IR OUT OUT -> GPIO26
// E18-D80NK usually outputs LOW when blocked.

#define IR_IN_PIN  27
#define IR_OUT_PIN 26

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(IR_IN_PIN, INPUT_PULLUP);
  pinMode(IR_OUT_PIN, INPUT_PULLUP);

  Serial.println("=== TEST ONLY IR SENSORS ===");
  Serial.println("Expected: LOW = blocked, HIGH = clear");
}

void loop() {
  int inVal = digitalRead(IR_IN_PIN);
  int outVal = digitalRead(IR_OUT_PIN);

  Serial.print("IR_IN=");
  Serial.print(inVal == LOW ? "LOW/BLOCKED" : "HIGH/CLEAR");
  Serial.print(" | IR_OUT=");
  Serial.println(outVal == LOW ? "LOW/BLOCKED" : "HIGH/CLEAR");

  delay(300);
}
