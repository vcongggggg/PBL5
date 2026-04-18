// ESP32 Parking Barrier Controller (modular structure)
// setup()/loop() here, services split into .h/.cpp files

#include "api_client.h"
#include "config.h"
#include "gate_controller.h"
#include "network_service.h"
#include "rfid_service.h"

bool prevIrIn = false;
bool prevIrOut = false;
bool fireAlertActive = false;
unsigned long lastFireAlertSentAt = 0;
String lastDirectionHint = "in";

void setupInputPins() {
  pinMode(IR_IN_PIN, INPUT);
  pinMode(IR_OUT_PIN, INPUT);
  pinMode(FIRE_SENSOR_PIN, INPUT);
}

void handleIrSensors() {
  bool irInNow = digitalRead(IR_IN_PIN) == HIGH;
  bool irOutNow = digitalRead(IR_OUT_PIN) == HIGH;

  if (irInNow && !prevIrIn) {
    lastDirectionHint = "in";
    Serial.println("IR IN triggered");
    sendCarDetected("in", "gate_in");
  }
  prevIrIn = irInNow;

  if (irOutNow && !prevIrOut) {
    lastDirectionHint = "out";
    Serial.println("IR OUT triggered");
    sendCarDetected("out", "gate_out");
  }
  prevIrOut = irOutNow;
}

void handleRfid() {
  String uid = readRfidUid();
  if (uid.length() > 0) {
    sendRfidScan(uid, lastDirectionHint);
    delay(500);
  }
}

void handleFireSensor() {
  int fireValue = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireValue == HIGH);

  if (fireDetected && !fireAlertActive) {
    fireAlertActive = true;
    Serial.println("FIRE DETECTED! Open all gates + turn on relays");
    openGateIn();
    openGateOut();
    setAlertRelays(true);
    sendFireAlert(DEVICE_ID, fireValue);
  }

  if (!fireDetected && fireAlertActive) {
    fireAlertActive = false;
    Serial.println("Fire cleared. Turn off relays");
    setAlertRelays(false);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  connectWifi();
  setupInputPins();
  initGateHardware();
  initRfid();
}

void loop() {
  handleIrSensors();
  handleRfid();
  handleFireSensor();
  handleAutoClose(fireAlertActive);
  delay(50);
}

