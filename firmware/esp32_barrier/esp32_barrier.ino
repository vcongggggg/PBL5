// ESP32 Parking Barrier Controller (modular structure with MQTT)

#include "config.h"
#include "gate_controller.h"
#include "network_service.h"
#include "rfid_service.h"
#include "buzzer_service.h"
#include "mqtt_service.h"

// Global variables
bool irInEventSentWhileBlocked = false;
bool irOutEventSentWhileBlocked = false;
bool fireAlertActive = false;
unsigned long lastFireAlertSentAt = 0;
unsigned long fireLowStartedAt = 0;
unsigned long fireHighStartedAt = 0;
unsigned long lastFireTelemetrySentAt = 0;
unsigned long lastIrInSentAt = 0;
unsigned long lastIrOutSentAt = 0;
unsigned long irInLowStartedAt = 0;
unsigned long irOutLowStartedAt = 0;
unsigned long lastRfidSentAt = 0;
String lastRfidUid = "";
String lastDirectionHint = "in";

static const unsigned long IR_EVENT_COOLDOWN_MS = 3000;
static const unsigned long RFID_EVENT_COOLDOWN_MS = 3000;

// Hàm xử lý reset báo động cháy gọi từ mqtt_service callback
void resetFireAlarmLocal() {
  Serial.println("[MQTT] Yêu cầu tắt báo động cháy (Reset Fire alarm) thành công.");
  fireAlertActive = false;
  fireLowStartedAt = 0;
  fireHighStartedAt = 0;
  setAlertRelays(false);
  buzzerFireAlarm(false);
  closeGateIn();
  closeGateOut();
}

void setupInputPins() {
  pinMode(IR_IN_PIN, INPUT_PULLUP);
  pinMode(IR_OUT_PIN, INPUT_PULLUP);
  pinMode(FIRE_SENSOR_PIN, INPUT_PULLUP);
  pinMode(FIRE_ANALOG_PIN, INPUT);
}

void handleIrSensors() {
  // Khi đang cháy, bỏ qua xử lý IR để tránh xung đột
  if (fireAlertActive) return;

  // Cảm biến E18-D80NK thường trả về LOW khi có vật cản
  bool irInNow = (digitalRead(IR_IN_PIN) == LOW);
  bool irOutNow = (digitalRead(IR_OUT_PIN) == LOW);
  unsigned long now = millis();

  if (irInNow && irInLowStartedAt == 0) {
    irInLowStartedAt = now;
  } else if (!irInNow) {
    irInLowStartedAt = 0;
    irInEventSentWhileBlocked = false;
  }

  if (irInNow && !irInEventSentWhileBlocked && irInLowStartedAt > 0 && (now - irInLowStartedAt >= IR_CONFIRM_MS) && (now - lastIrInSentAt > IR_EVENT_COOLDOWN_MS)) {
    lastIrInSentAt = now;
    irInEventSentWhileBlocked = true;
    lastDirectionHint = "in";
    Serial.println("[IR] Xe đang vào -> Kích hoạt camera cổng VÀO");
    buzzerBeep();  // Beep 1 lần ngắn báo phát hiện xe
    publishCarDetected("in");
  }
  if (irOutNow && irOutLowStartedAt == 0) {
    irOutLowStartedAt = now;
  } else if (!irOutNow) {
    irOutLowStartedAt = 0;
    irOutEventSentWhileBlocked = false;
  }

  if (irOutNow && !irOutEventSentWhileBlocked && irOutLowStartedAt > 0 && (now - irOutLowStartedAt >= IR_CONFIRM_MS) && (now - lastIrOutSentAt > IR_EVENT_COOLDOWN_MS)) {
    lastIrOutSentAt = now;
    irOutEventSentWhileBlocked = true;
    lastDirectionHint = "out";
    Serial.println("[IR] Xe đang ra -> Kích hoạt camera cổng RA");
    buzzerBeep();  // Beep 1 lần ngắn báo phát hiện xe
    publishCarDetected("out");
  }
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
    if (publishRfidScan(uid, lastDirectionHint)) {
      buzzerDoubleBeep();  // Beep 2 lần nhanh báo gửi MQTT thành công
    } else {
      buzzerLongBeep();    // Beep dài báo lỗi kết nối mạng (MQTT disconnected)
    }
  }
}

void handleFireSensor() {
  int fireValue = digitalRead(FIRE_SENSOR_PIN);
  int fireAnalogValue = analogRead(FIRE_ANALOG_PIN);
  bool fireDigitalDetected = (fireValue == HIGH); // HIGH khi phát hiện lửa (Active High)
  bool fireAnalogDetected = (fireAnalogValue <= FIRE_ANALOG_ALERT_THRESHOLD);
  bool fireDetected = fireDigitalDetected || fireAnalogDetected;

  unsigned long now = millis();
  if (now - lastFireTelemetrySentAt >= FIRE_TELEMETRY_INTERVAL_MS) {
    publishFireTelemetry(fireValue, fireAnalogValue, fireDetected, fireAlertActive);
    lastFireTelemetrySentAt = now;
  }

  if (fireDetected) {
    fireHighStartedAt = 0;
    if (fireLowStartedAt == 0) {
      fireLowStartedAt = now;
    }
  } else {
    fireLowStartedAt = 0;
    if (fireAlertActive && fireHighStartedAt == 0) {
      fireHighStartedAt = now;
    }
  }

  if (fireDetected && !fireAlertActive && fireLowStartedAt > 0 && (now - fireLowStartedAt >= FIRE_CONFIRM_MS)) {
    fireAlertActive = true;
    Serial.println("PHÁT HIỆN HỎA HOẠN! Mở toàn bộ cổng + kích hoạt còi + đèn báo động!");
    openGateIn();
    openGateOut();
    setAlertRelays(true);
    buzzerFireAlarm(true);  // Bật còi báo cháy liên tục

    // Gửi cảnh báo lên Backend qua MQTT (cooldown 10s)
    if (now - lastFireAlertSentAt > FIRE_ALERT_COOLDOWN_MS) {
      publishFireAlert(fireAnalogValue);
      lastFireAlertSentAt = now;
    }
  }

  if (fireAlertActive && !fireDetected && fireHighStartedAt > 0 && (now - fireHighStartedAt >= FIRE_CLEAR_CONFIRM_MS)) {
    Serial.println("[FIRE] Sensor clear is stable. Alarm stays active until guard resets it.");
    fireHighStartedAt = 0;
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
