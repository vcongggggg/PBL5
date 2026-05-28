#ifndef CONFIG_H
#define CONFIG_H

// ================== WIFI & BACKEND ==================
static const char *DEVICE_ID = "esp32-barrier-01";
static const char *API_KEY = "pbl5_secure_key_12345";

// ================== PIN MAP ==================
// Gate IN
static const int SERVO_IN_PIN = 14;
static const int IR_IN_PIN = 27;

// Gate OUT
static const int SERVO_OUT_PIN = 13;
static const int IR_OUT_PIN = 26;

// Fire + relay
static const int FIRE_SENSOR_PIN = 33;
static const int RELAY_CH1_PIN = 32;
static const int RELAY_CH2_PIN = 25;

// RFID RC522 (SPI)
static const int RFID_SS_PIN = 5;
static const int RFID_RST_PIN = 22;

// Buzzer
static const int BUZZER_PIN = 4;

// ================== BEHAVIOR ==================
static const int ANGLE_CLOSED = 0;
static const int ANGLE_OPEN = 80;
static const unsigned long AUTO_CLOSE_MS = 8000;
static const unsigned long FIRE_ALERT_COOLDOWN_MS = 10000;

#endif

