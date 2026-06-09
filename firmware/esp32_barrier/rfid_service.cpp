#include <SPI.h>
#include <MFRC522.h>

#include "config.h"
#include "rfid_service.h"

static MFRC522 mfrc522(RFID_SS_PIN, RFID_RST_PIN);

void initRfid() {
  SPI.begin(18, 19, 23, RFID_SS_PIN);
  mfrc522.PCD_Init();

  byte version = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  Serial.print("[RFID] RC522 VersionReg: 0x");
  Serial.println(version, HEX);

  if (version == 0x00 || version == 0xFF) {
    Serial.println("[RFID] WARNING: RC522 not detected. Check 3.3V, GND, SDA=5, SCK=18, MOSI=23, MISO=19, RST=22.");
  } else {
    Serial.println("[RFID] RC522 initialized and ready.");
  }
}

String readRfidUid() {
  // Kiểm tra sức khỏe đầu đọc RFID định kỳ
  byte version = mfrc522.PCD_ReadRegister(mfrc522.VersionReg);
  if (version == 0x00 || version == 0xFF) {
    static unsigned long lastRfidReinit = 0;
    unsigned long now = millis();
    if (now - lastRfidReinit > 5000) {
      lastRfidReinit = now;
      Serial.println("[RFID] WARNING: RC522 hung or disconnected! Re-initializing...");
      mfrc522.PCD_Init();
      delay(50);
    }
    return "";
  }

  if (!mfrc522.PICC_IsNewCardPresent()) return "";
  if (!mfrc522.PICC_ReadCardSerial()) return "";

  String uid = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(mfrc522.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
  return uid;
}

