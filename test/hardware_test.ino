/*
 * CHƯƠNG TRÌNH KIỂM TRA PHẦN CỨNG (HARDWARE TEST)
 * Dành cho: PBL5 Smart Parking
 * Kiểm tra: 2 Servo, 2 Cảm biến IR (E18-D80NK), 1 RFID RC522
 */

#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>

// --- CẤU HÌNH CHÂN (Theo đúng sơ đồ đã nối) ---
const int SERVO_IN_PIN = 14;
const int SERVO_OUT_PIN = 13;
const int IR_IN_PIN = 27;
const int IR_OUT_PIN = 26;

const int RFID_SS_PIN = 5;
const int RFID_RST_PIN = 22;

// --- KHỞI TẠO ĐỐI TƯỢNG ---
Servo servoIn;
Servo servoOut;
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== KIỂM TRA HỆ THỐNG BẮT ĐẦU ===");

  // 1. Cấu hình Cảm biến IR (Dùng PULLUP vì E18-D80NK là NPN)
  pinMode(IR_IN_PIN, INPUT_PULLUP);
  pinMode(IR_OUT_PIN, INPUT_PULLUP);
  Serial.println("1. Cảm biến IR: Đã sẵn sàng.");

  // 2. Cấu hình Servo
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoIn.setPeriodHertz(50);
  servoOut.setPeriodHertz(50);
  
  servoIn.attach(SERVO_IN_PIN, 500, 2400);
  servoOut.attach(SERVO_OUT_PIN, 500, 2400);
  
  Serial.println("2. Servo: Đang kiểm tra chuyển động (Quay 0 -> 90 -> 0)...");
  servoIn.write(90);
  servoOut.write(90);
  delay(1000);
  servoIn.write(0);
  servoOut.write(0);
  delay(1000);
  Serial.println("   Servo: Kiểm tra xong.");

  // 3. Cấu hình RFID
  SPI.begin();
  rfid.PCD_Init();
  Serial.print("3. RFID RC522: ");
  if (rfid.PCD_PerformSelfTest()) {
    Serial.println("Kết nối THÀNH CÔNG.");
  } else {
    Serial.println("CẢNH BÁO: Không tìm thấy module RFID (Kiểm tra lại dây SPI).");
  }

  Serial.println("\n--- BẮT ĐẦU QUÉT THIẾT BỊ (Xem kết quả bên dưới) ---");
  Serial.println("Hãy thử: Che tay trước cảm biến IR HOẶC quẹt thẻ RFID.");
}

void loop() {
  // === TEST CẢM BIẾN IR ===
  // Logic: E18-D80NK trả về LOW khi có vật cản
  bool carIn = (digitalRead(IR_IN_PIN) == LOW);
  bool carOut = (digitalRead(IR_OUT_PIN) == LOW);

  if (carIn) {
    Serial.println("[IR] -> PHÁT HIỆN xe ở cổng VÀO");
    delay(200); // Tránh in log quá nhanh
  }

  if (carOut) {
    Serial.println("[IR] -> PHÁT HIỆN xe ở cổng RA");
    delay(200);
  }

  // === TEST RFID ===
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.print("[RFID] -> Đã quét thẻ! UID: ");
    String content = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      Serial.print(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
      Serial.print(rfid.uid.uidByte[i], HEX);
    }
    Serial.println();
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  delay(100);
}
