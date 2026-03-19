// ESP32 Parking Barrier Controller
// Nhóm vi điều khiển PBL5

#include <WiFi.h>
#include <HTTPClient.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ================== CẤU HÌNH WI-FI & BACKEND ==================
// TODO: Sửa lại theo mạng Wi-Fi và server backend của nhóm web
const char *WIFI_SSID = "Galaxy A13 47BD";
const char *WIFI_PASS = "cong,123321";

// Địa chỉ server FastAPI (ví dụ: máy laptop trong cùng mạng LAN)
// Ví dụ: "http://192.168.1.100:8000/api/esp/events"
const char *BACKEND_URL_EVENT = "http://10.120.151.115:8000/api/esp/events";
const char *BACKEND_URL_MANUAL_OPEN = "http://10.120.151.115:8000/api/esp/manual-open";

// ID định danh cho cổng barrier này
const char *DEVICE_ID = "gate-1";

// ================== KHAI BÁO CHÂN PHẦN CỨNG ==================
// Có thể thay đổi tuỳ cách đấu dây, nhưng nhớ sửa cả code
const int SERVO_PIN = 14;    // Servo MG996R
const int IR_PIN = 27;       // Cảm biến IR phát hiện xe
const int BUTTON_PIN = 26;   // Nút mở cổng cưỡng bách (nhấn = LOW)

// Servo
Servo barrierServo;
const int ANGLE_CLOSED = 0;   // Góc đóng barrier
const int ANGLE_OPEN = 80;    // Góc mở barrier (tuỳ chỉnh theo cơ khí)

// LCD I2C 20x4 (địa chỉ phổ biến 0x27, có module có thể là 0x3F)
LiquidCrystal_I2C lcd(0x27, 20, 4);

// ================== BIẾN TRẠNG THÁI ==================
bool gateOpen = false;
unsigned long lastOpenMillis = 0;
const unsigned long AUTO_CLOSE_MS = 8000;  // Tự đóng sau 8 giây

// ================== HÀM KẾT NỐI WI-FI ==================
void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi connected, IP: ");
  Serial.println(WiFi.localIP());
}

// ================== HÀM KHỞI TẠO PHẦN CỨNG ==================
void setupHardware() {
  pinMode(IR_PIN, INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  barrierServo.attach(SERVO_PIN);
  barrierServo.write(ANGLE_CLOSED);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Parking System");
  lcd.setCursor(0, 1);
  lcd.print("Waiting for car");
}

// ================== CÁC HÀM ĐIỀU KHIỂN BARRIER ==================
void openGate() {
  barrierServo.write(ANGLE_OPEN);
  gateOpen = true;
  lastOpenMillis = millis();
}

void closeGate() {
  barrierServo.write(ANGLE_CLOSED);
  gateOpen = false;
}

// ================== HÀM HIỂN THỊ LCD ==================
void showStatus(const String &line1, const String &line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

// ================== GỬI SỰ KIỆN MỞ CƯỠNG BÁCH ==================
void sendManualOpen() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(BACKEND_URL_MANUAL_OPEN);
  http.addHeader("Content-Type", "application/json");

  String body = "{";
  body += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  body += "\"reason\":\"button_pressed\"}";

  int code = http.POST(body);
  Serial.printf("Manual open POST -> %d\n", code);
  http.end();
}

// ================== GỬI SỰ KIỆN XE ĐẾN LÊN BACKEND ==================
void sendCarDetected() {
  if (WiFi.status() != WL_CONNECTED) {
    showStatus("WiFi error", "Manual only");
    return;
  }

  showStatus("Car detected", "Waiting server");

  HTTPClient http;
  http.begin(BACKEND_URL_EVENT);
  http.addHeader("Content-Type", "application/json");

  // Đơn giản: direction tạm thời cố định "in"
  String body = "{";
  body += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  body += "\"event_type\":\"car_detected\",";
  body += "\"direction\":\"in\"";
  body += "}";

  int code = http.POST(body);
  String resp = http.getString();
  http.end();

  Serial.printf("Event POST -> %d\n", code);
  Serial.println(resp);

  if (code == 200) {
    // Parse rất đơn giản bằng cách tìm chuỗi.
    // Sau này có thể thay bằng ArduinoJson nếu cần tách plate, message để hiển thị.
    if (resp.indexOf("\"action\":\"open\"") != -1) {
      openGate();
      showStatus("Gate OPEN", "Welcome");
    } else {
      showStatus("Access denied", "");
      closeGate();
    }
  } else {
    showStatus("Server error", "Manual only");
  }
}

// ================== SETUP ==================
void setup() {
  Serial.begin(115200);
  delay(1000);
  connectWifi();
  setupHardware();
}

// ================== VÒNG LẶP CHÍNH ==================
void loop() {
  static bool prevIR = false;

  // Đọc cảm biến IR
  bool carNow = digitalRead(IR_PIN) == HIGH;

  // Cạnh lên: lúc trước không có, giờ có -> xe mới tới
  if (carNow && !prevIR) {
    Serial.println("Car detected");
    sendCarDetected();
  }
  prevIR = carNow;

  // Nút nhấn mở cưỡng bách (nhấn = LOW)
  if (digitalRead(BUTTON_PIN) == LOW) {
    Serial.println("Manual button pressed");
    openGate();
    showStatus("Manual OPEN", "");
    sendManualOpen();
    delay(500);  // Chống dội phím
  }

  // Tự đóng sau AUTO_CLOSE_MS
  if (gateOpen && (millis() - lastOpenMillis > AUTO_CLOSE_MS)) {
    closeGate();
    showStatus("Gate CLOSED", "Waiting car");
  }

  delay(50);
}

