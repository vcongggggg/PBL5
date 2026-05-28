#include <WiFi.h>
#include <WiFiManager.h>
#include <Preferences.h>

#include "config.h"
#include "network_service.h"

char backend_ip[40] = "192.168.0.141"; // Giá trị mặc định dự phòng

void connectWifi() {
  // 1. Đọc Backend IP từ NVS Preferences
  Preferences prefs;
  prefs.begin("parking", false);
  String saved_ip = prefs.getString("backend_ip", "192.168.0.141");
  saved_ip.toCharArray(backend_ip, 40);
  prefs.end();

  // 2. Khởi tạo WiFiManager
  WiFiManager wm;
  wm.setConfigPortalTimeout(180); // Đợi tối đa 3 phút ở cổng cấu hình

  // 3. Định nghĩa ô nhập liệu Backend IP trên giao diện Web Portal
  WiFiManagerParameter custom_backend_ip("backend_ip", "Backend IP Address", backend_ip, 40);
  wm.addParameter(&custom_backend_ip);

  // 4. Kích hoạt tự động kết nối (nếu không có WiFi sẽ phát AP "Smart_Parking_Setup")
  Serial.println("[WIFI] Auto-connecting...");
  bool res = wm.autoConnect("Smart_Parking_Setup");

  if (!res) {
    Serial.println("[WIFI] Failed to connect or timeout. Restarting ESP32...");
    delay(3000);
    ESP.restart();
  }

  // 5. Kết nối thành công -> Đọc tham số mới nhập từ Portal và lưu vào flash
  String new_ip = String(custom_backend_ip.getValue());
  new_ip.trim();
  if (new_ip.length() > 0 && new_ip != saved_ip) {
    new_ip.toCharArray(backend_ip, 40);
    prefs.begin("parking", false);
    prefs.putString("backend_ip", new_ip);
    prefs.end();
    Serial.printf("[WIFI] Updated and saved new Backend IP: %s\n", backend_ip);
  } else {
    Serial.printf("[WIFI] Using Backend IP: %s\n", backend_ip);
  }

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
    Serial.println("[WIFI] Connection lost. WiFiManager autoConnect will handle reconnect...");
    // Gọi lại connectWifi để tự động kết nối lại hoặc mở lại Portal cấu hình nếu cần
    connectWifi();
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
