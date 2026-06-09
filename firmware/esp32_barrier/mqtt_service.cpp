#include <WiFi.h>
#include <PubSubClient.h>

#include "config.h"
#include "network_service.h"
#include "mqtt_service.h"
#include "gate_controller.h"

// Hàm từ esp32_barrier.ino để xử lý reset báo động cháy đồng bộ
extern void resetFireAlarmLocal();

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String topicStr = String(topic);
  String payloadStr = "";
  for (unsigned int i = 0; i < length; i++) {
    payloadStr += (char)payload[i];
  }
  Serial.printf("[MQTT] Callback topic: %s -> %s\n", topic, payloadStr.c_str());

  if (topicStr.equals(MQTT_TOPIC_COMMAND_OPEN)) {
    payloadStr.replace(" ", "");
    payloadStr.replace("\n", "");
    payloadStr.replace("\r", "");
    payloadStr.replace("\t", "");

    if (payloadStr.indexOf("\"gate\":\"in\"") != -1) {
      Serial.println("[MQTT] Nhận lệnh mở cổng VÀO");
      openGateIn();
    } else if (payloadStr.indexOf("\"gate\":\"out\"") != -1) {
      Serial.println("[MQTT] Nhận lệnh mở cổng RA");
      openGateOut();
    } else {
      Serial.println("[MQTT] Không nhận diện được gate trong lệnh open_gate.");
    }
  } else if (topicStr.equals(MQTT_TOPIC_COMMAND_RESET_FIRE)) {
    Serial.println("[MQTT] Nhận lệnh tắt báo động cháy (Reset Fire)");
    resetFireAlarmLocal();
  }
}

void reconnectMqtt() {
  static unsigned long lastMqttRetry = 0;
  unsigned long now = millis();
  if (now - lastMqttRetry < 5000) return; // Thử kết nối lại mỗi 5 giây (không chặn luồng chính)
  lastMqttRetry = now;

  if (isWifiConnected() && !mqttClient.connected()) {
    Serial.printf("[MQTT] Đang kết nối tới Broker %s:%d...\n", mqtt_broker, mqtt_port);
    mqttClient.setServer(mqtt_broker, mqtt_port);
    mqttClient.setCallback(mqttCallback);
    
    if (mqttClient.connect(MQTT_CLIENT_ID, API_KEY, NULL)) {
      Serial.println("[MQTT] Kết nối thành công!");
      mqttClient.subscribe(MQTT_TOPIC_COMMAND_OPEN);
      mqttClient.subscribe(MQTT_TOPIC_COMMAND_RESET_FIRE);
    } else {
      Serial.printf("[MQTT] Kết nối thất bại, state=%d. Sẽ thử lại sau 5s.\n", mqttClient.state());
    }
  }
}

void setupMqtt() {
  mqttClient.setServer(mqtt_broker, mqtt_port);
  mqttClient.setCallback(mqttCallback);
}

void loopMqtt() {
  if (!mqttClient.connected()) {
    reconnectMqtt();
  } else {
    mqttClient.loop();
  }
}

void publishCarDetected(const String &direction) {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Lỗi: Chưa kết nối tới broker. Bỏ qua publish car_detected.");
    return;
  }
  String gateId = (direction == "in") ? "gate_in" : "gate_out";
  String body = "{";
  body += "\"device_id\":\"" + String(MQTT_CLIENT_ID) + "\",";
  body += "\"event_type\":\"car_detected\",";
  body += "\"direction\":\"" + direction + "\",";
  body += "\"gate_id\":\"" + gateId + "\"";
  body += "}";

  mqttClient.publish(MQTT_TOPIC_CAR_DETECTED, body.c_str(), false);
  Serial.printf("[MQTT] Đã gửi sự kiện phát hiện xe cổng (%s)\n", direction.c_str());
}

void publishRfidScan(const String &uid, const String &directionHint) {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Lỗi: Chưa kết nối tới broker. Bỏ qua publish rfid_scan.");
    return;
  }
  String gateId = (directionHint == "in") ? "gate_in" : "gate_out";
  String body = "{";
  body += "\"device_id\":\"" + String(MQTT_CLIENT_ID) + "\",";
  body += "\"uid\":\"" + uid + "\",";
  body += "\"direction\":\"" + directionHint + "\",";
  body += "\"gate_id\":\"" + gateId + "\"";
  body += "}";

  mqttClient.publish(MQTT_TOPIC_RFID_SCAN, body.c_str(), false);
  Serial.printf("[MQTT] Đã gửi dữ liệu thẻ RFID (UID: %s)\n", uid.c_str());
}

void publishFireAlert(int sensorValue) {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Lỗi: Chưa kết nối tới broker. Bỏ qua publish fire_alert.");
    return;
  }
  String body = "{";
  body += "\"device_id\":\"" + String(MQTT_CLIENT_ID) + "\",";
  body += "\"sensor_value\":" + String(sensorValue) + ",";
  body += "\"message\":\"Fire sensor triggered\"";
  body += "}";

  mqttClient.publish(MQTT_TOPIC_FIRE_ALERT, body.c_str(), false);
  Serial.println("[MQTT] Đã gửi cảnh báo hoả hoạn!");
}

void publishFireTelemetry(int digitalValue, int analogValue, bool fireDetected, bool fireAlertActive) {
  if (!mqttClient.connected()) {
    return;
  }

  String body = "{";
  body += "\"device_id\":\"" + String(MQTT_CLIENT_ID) + "\",";
  body += "\"digital_value\":" + String(digitalValue) + ",";
  body += "\"analog_value\":" + String(analogValue) + ",";
  body += "\"fire_detected\":" + String(fireDetected ? "true" : "false") + ",";
  body += "\"fire_alert_active\":" + String(fireAlertActive ? "true" : "false");
  body += "}";

  mqttClient.publish(MQTT_TOPIC_FIRE_TELEMETRY, body.c_str(), false);
}
