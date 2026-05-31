// TEST ALL LOCAL HARDWARE - NO WIFI, NO MQTT, NO BACKEND
// Pins match firmware/esp32_barrier/config.h

#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>

#define SERVO_IN_PIN    14
#define SERVO_OUT_PIN   13
#define IR_IN_PIN       27
#define IR_OUT_PIN      26
#define FIRE_SENSOR_PIN 33
#define ALERT_CH1_PIN   32
#define ALERT_CH2_PIN   25
#define BUZZER_PIN      4
#define RFID_SS_PIN     5
#define RFID_RST_PIN    22

Servo servoIn;
Servo servoOut;
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

void beep(int ms = 100) {
  digitalWrite(BUZZER_PIN, HIGH);
  delay(ms);
  digitalWrite(BUZZER_PIN, LOW);
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(IR_IN_PIN, INPUT_PULLUP);
  pinMode(IR_OUT_PIN, INPUT_PULLUP);
  pinMode(FIRE_SENSOR_PIN, INPUT_PULLUP);
  pinMode(ALERT_CH1_PIN, OUTPUT);
  pinMode(ALERT_CH2_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(ALERT_CH1_PIN, LOW);
  digitalWrite(ALERT_CH2_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoIn.setPeriodHertz(50);
  servoOut.setPeriodHertz(50);
  servoIn.attach(SERVO_IN_PIN, 500, 2400);
  servoOut.attach(SERVO_OUT_PIN, 500, 2400);
  servoIn.write(0);
  servoOut.write(0);

  SPI.begin();
  rfid.PCD_Init();

  Serial.println("=== PBL5 ALL HARDWARE TEST ===");
  Serial.println("IR: LOW=blocked. Fire: LOW=fire. RFID: show UID.");
  Serial.println("Servo quick self-test...");
  servoIn.write(80);
  servoOut.write(80);
  beep(150);
  delay(1000);
  servoIn.write(0);
  servoOut.write(0);
  delay(500);

  byte version = rfid.PCD_ReadRegister(rfid.VersionReg);
  Serial.print("RFID VersionReg=0x");
  Serial.println(version, HEX);
  if (version == 0x00 || version == 0xFF) {
    Serial.println("RFID not detected. Check 3.3V/GND/SPI wires.");
  }
}

void loop() {
  static unsigned long lastPrint = 0;
  unsigned long now = millis();

  bool irInBlocked = (digitalRead(IR_IN_PIN) == LOW);
  bool irOutBlocked = (digitalRead(IR_OUT_PIN) == LOW);
  bool fireDetected = (digitalRead(FIRE_SENSOR_PIN) == LOW);

  if (now - lastPrint >= 500) {
    Serial.print("IR_IN=");
    Serial.print(irInBlocked ? "BLOCKED" : "CLEAR");
    Serial.print(" | IR_OUT=");
    Serial.print(irOutBlocked ? "BLOCKED" : "CLEAR");
    Serial.print(" | FIRE=");
    Serial.println(fireDetected ? "FIRE" : "NORMAL");
    lastPrint = now;
  }

  if (irInBlocked) {
    servoIn.write(80);
  } else {
    servoIn.write(0);
  }

  if (irOutBlocked) {
    servoOut.write(80);
  } else {
    servoOut.write(0);
  }

  digitalWrite(BUZZER_PIN, fireDetected ? HIGH : LOW);
  digitalWrite(ALERT_CH1_PIN, fireDetected ? HIGH : LOW);
  digitalWrite(ALERT_CH2_PIN, fireDetected ? HIGH : LOW);

  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print("RFID UID=");
    for (byte i = 0; i < rfid.uid.size; i++) {
      if (rfid.uid.uidByte[i] < 0x10) Serial.print("0");
      Serial.print(rfid.uid.uidByte[i], HEX);
    }
    Serial.println();
    beep(120);
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  delay(50);
}
