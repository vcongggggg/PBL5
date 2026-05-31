// ESP32 Parking Barrier Controller (modular structure with MQTT)

#include "config.h"
#include "gate_controller.h"
#include "network_service.h"
#include "rfid_service.h"
#include "buzzer_service.h"
#include "mqtt_service.h"

// Global variables
bool prevIrIn = false;
bool prevIrOut = false;
bool fireAlertActive = false;
unsigned long lastFireAlertSentAt = 0;
unsigned long lastIrInSentAt = 0;
unsigned long lastIrOutSentAt = 0;
unsigned long lastRfidSentAt = 0;
String lastRfidUid = "";
String lastDirectionHint = "in";

static const unsigned long IR_EVENT_COOLDOWN_MS = 3000;
static const unsigned long RFID_EVENT_COOLDOWN_MS = 3000;

// Hàm xử lý reset báo động cháy gọi từ mqtt_service callback
void resetFireAlarmLocal() {
  Serial.println("[MQTT] Yêu cầu tắt báo động cháy (Reset Fire alarm) thành công.");
  fireAlertActive = false;
  setAlertRelays(false);
  buzzerFireAlarm(false);
  closeGateIn();
  closeGateOut();
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
  unsigned long now = millis();

  if (irInNow && !prevIrIn && (now - lastIrInSentAt > IR_EVENT_COOLDOWN_MS)) {
    lastIrInSentAt = now;
    lastDirectionHint = "in";
    Serial.println("[IR] Xe đang vào -> Kích hoạt camera cổng VÀO");
    buzzerBeep();  // Beep 1 lần ngắn báo phát hiện xe
    publishCarDetected("in");
    delay(500); // Debounce
  }
  prevIrIn = irInNow;

  if (irOutNow && !prevIrOut && (now - lastIrOutSentAt > IR_EVENT_COOLDOWN_MS)) {
    lastIrOutSentAt = now;
    lastDirectionHint = "out";
    Serial.println("[IR] Xe đang ra -> Kích hoạt camera cổng RA");
    buzzerBeep();  // Beep 1 lần ngắn báo phát hiện xe
    publishCarDetected("out");
    delay(500); // Debounce
  }
  prevIrOut = irOutNow;
}

void handleRfid() {
  // Khi đang cháy, bỏ qua RFID
  if (fireAlertActive) return;

  String uid = readRfidUid();
  if (uid.length() > 0) {
    unsigned long now = millis();
    if (uid == lastRfidUid && (now - lastRfidSentAt < RFID_EVENT_COOLDOWN_MS)) {
      return;
    }
    lastRfidUid = uid;
    lastRfidSentAt = now;
    buzzerBeep();  // Beep 1 lần ngắn báo đã quẹt thẻ thành công
    publishRfidScan(uid, lastDirectionHint);
    delay(500);
  }
}

void handleFireSensor() {
  int fireValue = digitalRead(FIRE_SENSOR_PIN);
  bool fireDetected = (fireValue == LOW); // LOW khi phát hiện lửa (Active Low)

  if (fireDetected && !fireAlertActive) {
    fireAlertActive = true;
    Serial.println("PHÁT HIỆN HỎA HOẠN! Mở toàn bộ cổng + kích hoạt còi + đèn báo động!");
    openGateIn();
    openGateOut();
    setAlertRelays(true);
    buzzerFireAlarm(true);  // Bật còi báo cháy liên tục

    // Gửi cảnh báo lên Backend qua MQTT (cooldown 10s)
    unsigned long now = millis();
    if (now - lastFireAlertSentAt > FIRE_ALERT_COOLDOWN_MS) {
      publishFireAlert(fireValue);
      lastFireAlertSentAt = now;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  connectWifi();
  setupMqtt();      // Khởi tạo máy chủ MQTT Client
  setupInputPins();
  initGateHardware();
  initRfid();
  initBuzzer();
}

void loop() {
  checkWifiReconnect();  // Kiểm tra reconnect Wi-Fi
  loopMqtt();            // Xử lý các gói tin MQTT và giữ kết nối
  handleIrSensors();
  handleRfid();
  handleFireSensor();
  handleAutoClose(fireAlertActive);
  handleBuzzerLoop();    // Vòng lặp điều khiển còi báo động
  delay(50);
}
