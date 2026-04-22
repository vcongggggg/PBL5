/**
 * @file esp32_barrier_sim.ino
 * @brief Wokwi simulation firmware for PBL5 Smart Parking System
 *
 * This is a standalone simulation version that removes WiFi/HTTP
 * dependencies (not supported in Wokwi) while keeping all hardware
 * logic intact.
 *
 * Hardware Map (matches config.h):
 *   Servo IN     -> GPIO 14
 *   Servo OUT    -> GPIO 13
 *   IR IN        -> GPIO 27  (PIR sensor in Wokwi)
 *   IR OUT       -> GPIO 26  (PIR sensor in Wokwi)
 *   RFID SS      -> GPIO 5
 *   RFID RST     -> GPIO 22
 *   Fire Sensor  -> GPIO 33  (Pushbutton in Wokwi)
 *   Relay CH1    -> GPIO 32
 *   Relay CH2    -> GPIO 25
 */

#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>

// ================== PIN MAP (from config.h) ==================
#define SERVO_IN_PIN    14
#define SERVO_OUT_PIN   13
#define IR_IN_PIN       27
#define IR_OUT_PIN      26
#define FIRE_SENSOR_PIN 33
#define RELAY_CH1_PIN   32
#define RELAY_CH2_PIN   25
#define RFID_SS_PIN     5
#define RFID_RST_PIN    22

// ================== BEHAVIOR ==================
#define ANGLE_CLOSED    0
#define ANGLE_OPEN      80
#define AUTO_CLOSE_MS   8000
#define FIRE_COOLDOWN_MS 10000

// ================== OBJECTS ==================
Servo gateInServo;
Servo gateOutServo;
MFRC522 mfrc522(RFID_SS_PIN, RFID_RST_PIN);

// ================== STATE ==================
bool gateInOpen = false;
bool gateOutOpen = false;
unsigned long gateInOpenedAt = 0;
unsigned long gateOutOpenedAt = 0;

bool prevIrIn = false;
bool prevIrOut = false;
bool fireAlertActive = false;
String lastDirectionHint = "in";

// ================== GATE CONTROL ==================
void openGateIn() {
  gateInServo.write(ANGLE_OPEN);
  gateInOpen = true;
  gateInOpenedAt = millis();
  Serial.println("[GATE] >> Gate IN OPENED");
}

void closeGateIn() {
  gateInServo.write(ANGLE_CLOSED);
  gateInOpen = false;
  Serial.println("[GATE] << Gate IN CLOSED");
}

void openGateOut() {
  gateOutServo.write(ANGLE_OPEN);
  gateOutOpen = true;
  gateOutOpenedAt = millis();
  Serial.println("[GATE] >> Gate OUT OPENED");
}

void closeGateOut() {
  gateOutServo.write(ANGLE_CLOSED);
  gateOutOpen = false;
  Serial.println("[GATE] << Gate OUT CLOSED");
}

void setAlertRelays(bool on) {
  digitalWrite(RELAY_CH1_PIN, on ? HIGH : LOW);
  digitalWrite(RELAY_CH2_PIN, on ? HIGH : LOW);
  Serial.printf("[RELAY] Relay CH1 & CH2: %s\n", on ? "ON" : "OFF");
}

void handleAutoClose() {
  if (fireAlertActive) return;
  unsigned long now = millis();
  if (gateInOpen && (now - gateInOpenedAt > AUTO_CLOSE_MS)) {
    closeGateIn();
  }
  if (gateOutOpen && (now - gateOutOpenedAt > AUTO_CLOSE_MS)) {
    closeGateOut();
  }
}

// ================== IR SENSORS ==================
void handleIrSensors() {
  bool irInNow = digitalRead(IR_IN_PIN) == HIGH;
  bool irOutNow = digitalRead(IR_OUT_PIN) == HIGH;

  if (irInNow && !prevIrIn) {
    lastDirectionHint = "in";
    Serial.println("[IR] >>> Car detected at ENTRANCE (IR IN triggered)");
    Serial.println("[SIM] Backend would call POST /api/esp/events {direction:in}");
    // In simulation, directly open the gate
    openGateIn();
  }
  prevIrIn = irInNow;

  if (irOutNow && !prevIrOut) {
    lastDirectionHint = "out";
    Serial.println("[IR] <<< Car detected at EXIT (IR OUT triggered)");
    Serial.println("[SIM] Backend would call POST /api/esp/events {direction:out}");
    // In simulation, directly open the gate
    openGateOut();
  }
  prevIrOut = irOutNow;
}

// ================== RFID ==================
void handleRfid() {
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  // Build UID string
  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
    if (i < mfrc522.uid.size - 1) uid += ":";
  }
  uid.toUpperCase();

  // Display card type
  MFRC522::PICC_Type piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);
  
  Serial.println("=========================================");
  Serial.printf("[RFID] Card UID: %s\n", uid.c_str());
  Serial.printf("[RFID] Card Type: %s\n", mfrc522.PICC_GetTypeName(piccType));
  Serial.printf("[RFID] Direction hint: %s\n", lastDirectionHint.c_str());
  Serial.println("[SIM] Backend would call POST /api/esp/rfid {uid, direction}");

  // In simulation, auto-open the appropriate gate
  if (lastDirectionHint == "in") {
    Serial.println("[RFID] -> Opening Gate IN for monthly pass holder");
    openGateIn();
  } else {
    Serial.println("[RFID] -> Opening Gate OUT for monthly pass holder");
    openGateOut();
  }
  Serial.println("=========================================");

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  delay(500);
}

// ================== FIRE SENSOR ==================
void handleFireSensor() {
  int fireValue = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireValue == HIGH);

  if (fireDetected && !fireAlertActive) {
    fireAlertActive = true;
    Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    Serial.println("[FIRE] !!! FIRE DETECTED !!!");
    Serial.println("[FIRE] Opening ALL gates + activating relays");
    Serial.println("[SIM] Backend would call POST /api/esp/fire-alert");
    Serial.println("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!");
    openGateIn();
    openGateOut();
    setAlertRelays(true);
  }

  if (!fireDetected && fireAlertActive) {
    fireAlertActive = false;
    Serial.println("[FIRE] Fire cleared. Turning off alert relays.");
    setAlertRelays(false);
  }
}

// ================== SETUP & LOOP ==================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=============================================");
  Serial.println("  PBL5 Smart Parking - Wokwi Simulation");
  Serial.println("=============================================");
  Serial.println();

  // Input pins
  pinMode(IR_IN_PIN, INPUT);
  pinMode(IR_OUT_PIN, INPUT);
  pinMode(FIRE_SENSOR_PIN, INPUT);

  // Relay pins
  pinMode(RELAY_CH1_PIN, OUTPUT);
  pinMode(RELAY_CH2_PIN, OUTPUT);
  digitalWrite(RELAY_CH1_PIN, LOW);
  digitalWrite(RELAY_CH2_PIN, LOW);

  // Servos
  gateInServo.attach(SERVO_IN_PIN);
  gateOutServo.attach(SERVO_OUT_PIN);
  gateInServo.write(ANGLE_CLOSED);
  gateOutServo.write(ANGLE_CLOSED);
  Serial.println("[INIT] Servos attached (Gate IN=GPIO14, Gate OUT=GPIO13)");

  // RFID
  SPI.begin();
  mfrc522.PCD_Init();
  byte v = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  Serial.printf("[INIT] RFID RC522 firmware version: 0x%02X\n", v);
  if (v == 0x00 || v == 0xFF) {
    Serial.println("[INIT] WARNING: RFID module not detected!");
  } else {
    Serial.println("[INIT] RFID RC522 ready");
  }

  Serial.println();
  Serial.println("[READY] System initialized. Waiting for events...");
  Serial.println("  - Wave at PIR sensor (IR IN/OUT) to detect cars");
  Serial.println("  - Tap RFID card for monthly pass scan");
  Serial.println("  - Press red button to simulate FIRE");
  Serial.println("=============================================");
  Serial.println();
}

void loop() {
  handleIrSensors();
  handleRfid();
  handleFireSensor();
  handleAutoClose();
  delay(50);
}
