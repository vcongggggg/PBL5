// ESP32 Parking Barrier Controller (modular structure)
// setup()/loop() here, services split into .h/.cpp files

#include <WebServer.h>
#include "api_client.h"
#include "config.h"
#include "gate_controller.h"
#include "network_service.h"
#include "rfid_service.h"
#include "buzzer_service.h"

// Global variables
bool prevIrIn = false;
bool prevIrOut = false;
bool fireAlertActive = false;
unsigned long lastFireAlertSentAt = 0;
String lastDirectionHint = "in";

WebServer server(80);

void handleOpenGate() {
  if (server.hasArg("gate")) {
    String gate = server.arg("gate");
    Serial.printf("[WEB] Remote manual open command for gate: %s\n", gate.c_str());
    if (gate == "in") {
      openGateIn();
      server.send(200, "text/plain", "Gate IN opening");
    } else if (gate == "out") {
      openGateOut();
      server.send(200, "text/plain", "Gate OUT opening");
    } else {
      server.send(400, "text/plain", "Invalid gate param");
    }
  } else {
    server.send(400, "text/plain", "Missing gate param");
  }
}

void handleResetFire() {
  Serial.println("[WEB] Fire alarm RESET received from Backend");
  fireAlertActive = false;
  setAlertRelays(false);
  buzzerFireAlarm(false);
  closeGateIn();
  closeGateOut();
  server.send(200, "text/plain", "Fire alarm reset OK");
}

void handleSetIP() {
  if (server.hasArg("ip")) {
    String new_ip = server.arg("ip");
    updateBackendIp(new_ip);
    server.send(200, "text/plain", "Backend IP successfully updated to: " + new_ip);
  } else {
    server.send(400, "text/plain", "Missing ip parameter");
  }
}

void setupWebServer() {
  server.on("/open-gate", handleOpenGate);
  server.on("/reset-fire", handleResetFire);
  server.on("/set-ip", handleSetIP);
  server.begin();
  Serial.println("ESP32 WebServer started on port 80");
}
void setupInputPins() {
  pinMode(IR_IN_PIN, INPUT_PULLUP);
  pinMode(IR_OUT_PIN, INPUT_PULLUP);
  pinMode(FIRE_SENSOR_PIN, INPUT_PULLUP);
}

void handleIrSensors() {
  // Khi đang cháy, bỏ qua xử lý IR để tránh xung đột
  if (fireAlertActive) return;

  // Cảm biến E18-D80NK thường trả về LOW khi có vật cản
  bool irInNow = (digitalRead(IR_IN_PIN) == LOW);
  bool irOutNow = (digitalRead(IR_OUT_PIN) == LOW);

  if (irInNow && !prevIrIn) {
    lastDirectionHint = "in";
    Serial.println("[IR] Xe dang vao -> Trigger camera IN");
    buzzerBeep();  // Beep 1 lần khi phát hiện xe
    sendCarDetected("in", "gate_in");
    delay(500); // Debounce
  }
  prevIrIn = irInNow;

  if (irOutNow && !prevIrOut) {
    lastDirectionHint = "out";
    Serial.println("[IR] Xe dang ra -> Trigger camera OUT");
    buzzerBeep();  // Beep 1 lần khi phát hiện xe
    sendCarDetected("out", "gate_out");
    delay(500); // Debounce
  }
  prevIrOut = irOutNow;
}

void handleRfid() {
  // Khi đang cháy, bỏ qua RFID
  if (fireAlertActive) return;

  String uid = readRfidUid();
  if (uid.length() > 0) {
    bool accepted = sendRfidScan(uid, lastDirectionHint);
    if (accepted) {
      buzzerDoubleBeep();  // Beep 2 lần = RFID hợp lệ
    } else {
      buzzerLongBeep();    // Beep dài = RFID bị từ chối
    }
    delay(500);
  }
}

void handleFireSensor() {
  int fireValue = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireValue == LOW); // LOW khi phát hiện lửa (Active Low)

  if (fireDetected && !fireAlertActive) {
    fireAlertActive = true;
    Serial.println("FIRE DETECTED! Open all gates + turn on relays + ALARM");
    openGateIn();
    openGateOut();
    setAlertRelays(true);
    buzzerFireAlarm(true);  // Bật báo động liên tục

    // Gửi cảnh báo lên Backend (chỉ gửi khi mới phát hiện, cooldown 10s)
    unsigned long now = millis();
    if (now - lastFireAlertSentAt > FIRE_ALERT_COOLDOWN_MS) {
      sendFireAlert(DEVICE_ID, fireValue);
      lastFireAlertSentAt = now;
    }
  }

  // KHÔNG tự tắt khi sensor LOW - phải chờ Backend gọi /reset-fire
  // Điều này tránh barrier đóng mở liên tục khi khói dao động
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  connectWifi();
  setupWebServer();
  setupInputPins();
  initGateHardware();
  initRfid();
  initBuzzer();  // Khởi tạo buzzer
}

void loop() {
  server.handleClient();
  checkWifiReconnect();  // Tự reconnect WiFi nếu mất kết nối
  handleIrSensors();
  handleRfid();
  handleFireSensor();
  handleAutoClose(fireAlertActive);
  handleBuzzerLoop();  // Xử lý âm thanh báo động cháy liên tục
  delay(50);
}
