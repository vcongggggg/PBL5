#include <SPI.h>
#include <MFRC522.h>

#include "config.h"
#include "rfid_service.h"

static MFRC522 mfrc522(RFID_SS_PIN, RFID_RST_PIN);

void initRfid() {
  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("RFID RC522 initialized");
}

String readRfidUid() {
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

