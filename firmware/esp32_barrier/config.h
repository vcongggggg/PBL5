#ifndef CONFIG_H
#define CONFIG_H

// ================== WIFI & BACKEND ==================
static const char *DEVICE_ID = "esp32-barrier-01";
static const char *API_KEY = "pbl5_secure_key_12345";

// ================== MQTT ==================
static const char *MQTT_CLIENT_ID = "esp32-barrier-01";
static const char *MQTT_TOPIC_CAR_DETECTED = "parking/device/esp32-barrier-01/event/car_detected";
static const char *MQTT_TOPIC_RFID_SCAN = "parking/device/esp32-barrier-01/event/rfid_scan";
static const char *MQTT_TOPIC_FIRE_ALERT = "parking/device/esp32-barrier-01/event/fire_alert";
static const char *MQTT_TOPIC_COMMAND_OPEN = "parking/device/esp32-barrier-01/command/open_gate";
static const char *MQTT_TOPIC_COMMAND_RESET_FIRE = "parking/device/esp32-barrier-01/command/reset_fire";

// ================== PIN MAP ==================
// Gate IN
static const int SERVO_IN_PIN = 14;
static const int IR_IN_PIN = 27;

// Gate OUT
static const int SERVO_OUT_PIN = 13;
static const int IR_OUT_PIN = 26;

// Fire sensor
static const int FIRE_SENSOR_PIN = 33;

// RFID RC522 (SPI)
static const int RFID_SS_PIN = 5;
static const int RFID_RST_PIN = 22;

// Buzzer
static const int BUZZER_PIN = 32;

// ================== BEHAVIOR ==================
static const int ANGLE_CLOSED = 0;
static const int ANGLE_OPEN = 80;
static const unsigned long AUTO_CLOSE_MS = 8000;
static const unsigned long FIRE_ALERT_COOLDOWN_MS = 10000;
static const unsigned long IR_CONFIRM_MS = 300;

#endif

