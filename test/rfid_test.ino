/**
 * @file rfid_test.ino
 * @brief Standalone test code for RFID-RC522 module with ESP32
 * 
 * Hardware Settings:
 * - SDA (SS) -> GPIO 5
 * - SCK      -> GPIO 18
 * - MOSI     -> GPIO 23
 * - MISO     -> GPIO 19
 * - RST      -> GPIO 22
 * - VCC      -> 3.3V
 * - GND      -> GND
 */

#include <SPI.h>
#include <MFRC522.h>

// Định nghĩa chân nối dựa trên config.h của dự án
#define SS_PIN    5
#define RST_PIN   22

MFRC522 mfrc522(SS_PIN, RST_PIN); // Tạo đối tượng MFRC522

void setup() {
  Serial.begin(115200);   // Khởi tạo Serial monitor
  while (!Serial);        // Đợi Serial sẵn sàng
  
  SPI.begin();            // Khởi tạo SPI bus
  mfrc522.PCD_Init();     // Khởi tạo MFRC522
  
  Serial.println("--- RFID RC522 TEST ---");
  Serial.println("Quẹt thẻ hoặc tag RFID để xem UID...");
  
  // Kiểm tra kết nối với module
  byte v = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  Serial.print("Phiên bản firmware: 0x");
  Serial.println(v, HEX);
  
  if (v == 0x00 || v == 0xFF) {
    Serial.println("!!! CẢNH BÁO: Không tìm thấy module RFID. Kiểm tra lại dây nối!");
  }
}

void loop() {
  // Kiểm tra xem có thẻ mới được đưa đến gần không
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // Đọc thông tin thẻ
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Hiển thị UID lên Serial Monitor
  Serial.print("UID của thẻ: ");
  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
    if (i < mfrc522.uid.size - 1) uid += ":";
  }
  uid.toUpperCase();
  Serial.println(uid);

  // Hiển thị kiểu thẻ
  MFRC522::PICC_Type piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);
  Serial.print("Kiểu thẻ: ");
  Serial.println(mfrc522.PICC_GetTypeName(piccType));

  // Dừng đọc thẻ hiện tại
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  Serial.println("-----------------------");
  delay(1000); // Đợi 1 giây trước khi đọc lần tiếp theo
}
