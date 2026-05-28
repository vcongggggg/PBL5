#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>

#include "config.h"
#include "network_service.h"

char backend_ip[40] = "192.168.0.141"; // Giá trị mặc định dự phòng
char mqtt_broker[40] = "broker.hivemq.com";
int mqtt_port = 1883;

void connectWifi() {
  // 1. Đọc tham số cấu hình từ NVS Preferences
  Preferences prefs;
  prefs.begin("parking", false);
  String saved_ip = prefs.getString("backend_ip", "192.168.0.141");
  saved_ip.toCharArray(backend_ip, 40);
  
  String saved_broker = prefs.getString("mqtt_broker", "broker.hivemq.com");
  saved_broker.toCharArray(mqtt_broker, 40);
  
  mqtt_port = prefs.getInt("mqtt_port", 1883);
  prefs.end();

  // 2. Khởi tạo WiFiManager
  WiFiManager wm;
  wm.setConfigPortalTimeout(180); // Đợi tối đa 3 phút ở cổng cấu hình

  // 3. Định nghĩa ô cấu hình trên giao diện Web Portal
  WiFiManagerParameter custom_backend_ip("backend_ip", "Backend IP Address", backend_ip, 40);
  WiFiManagerParameter custom_mqtt_broker("mqtt_broker", "MQTT Broker Address", mqtt_broker, 40);
  char port_str[8];
  sprintf(port_str, "%d", mqtt_port);
  WiFiManagerParameter custom_mqtt_port("mqtt_port", "MQTT Broker Port", port_str, 8);

  wm.addParameter(&custom_backend_ip);
  wm.addParameter(&custom_mqtt_broker);
  wm.addParameter(&custom_mqtt_port);

  // 4. Kích hoạt tự động kết nối (nếu không có WiFi sẽ phát AP "Smart_Parking_Setup")
  Serial.println("[WIFI] Auto-connecting...");
  bool res = wm.autoConnect("Smart_Parking_Setup");

  if (!res) {
    Serial.println("[WIFI] Failed to connect or timeout. Restarting ESP32...");
    delay(3000);
    ESP.restart();
  }

  // 5. Kết nối thành công -> Lưu lại các tham số
  String new_ip = String(custom_backend_ip.getValue());
  new_ip.trim();
  String new_broker = String(custom_mqtt_broker.getValue());
  new_broker.trim();
  int new_port_val = atoi(custom_mqtt_port.getValue());

  prefs.begin("parking", false);
  if (new_ip.length() > 0 && new_ip != saved_ip) {
    new_ip.toCharArray(backend_ip, 40);
    prefs.putString("backend_ip", new_ip);
    Serial.printf("[WIFI] Saved Backend IP: %s\n", backend_ip);
  }
  if (new_broker.length() > 0 && new_broker != saved_broker) {
    new_broker.toCharArray(mqtt_broker, 40);
    prefs.putString("mqtt_broker", new_broker);
    Serial.printf("[WIFI] Saved MQTT Broker: %s\n", mqtt_broker);
  }
  if (new_port_val > 0 && new_port_val != mqtt_port) {
    mqtt_port = new_port_val;
    prefs.putInt("mqtt_port", new_port_val);
    Serial.printf("[WIFI] Saved MQTT Port: %d\n", mqtt_port);
  }
  prefs.end();

  Serial.print("[WIFI] Connected! IP: ");
  Serial.println(WiFi.localIP());
}

bool isWifiConnected() {
  return WiFi.status() == WL_CONNECTED;
}

static unsigned long lastWifiCheck = 0;
static const unsigned long WIFI_CHECK_INTERVAL_MS = 10000;

void checkWifiReconnect() {
  unsigned long now = millis();
  if (now - lastWifiCheck < WIFI_CHECK_INTERVAL_MS) return;
  lastWifiCheck = now;
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WIFI] Connection lost. Reconnecting...");
    // Ở đây ta có thể gọi lại connectWifi() hoặc để WiFi tự động kết nối ở background nếu đã có cấu hình
    WiFi.begin();
  }
}

void updateBackendIp(String new_ip) {
  new_ip.trim();
  if (new_ip.length() > 0) {
    new_ip.toCharArray(backend_ip, 40);
    Preferences prefs;
    prefs.begin("parking", false);
    prefs.putString("backend_ip", new_ip);
    prefs.end();
    Serial.printf("[WIFI] Dynamically updated and saved new Backend IP: %s\n", backend_ip);
  }
}

void updateMqttBroker(String new_broker, int new_port) {
  new_broker.trim();
  if (new_broker.length() > 0) {
    new_broker.toCharArray(mqtt_broker, 40);
    mqtt_port = new_port;
    Preferences prefs;
    prefs.begin("parking", false);
    prefs.putString("mqtt_broker", new_broker);
    prefs.putInt("mqtt_port", new_port);
    prefs.end();
    Serial.printf("[WIFI] Dynamically updated MQTT Broker: %s:%d\n", mqtt_broker, mqtt_port);
  }
}
