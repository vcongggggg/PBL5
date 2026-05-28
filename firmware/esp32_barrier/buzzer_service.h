#ifndef BUZZER_SERVICE_H
#define BUZZER_SERVICE_H

// Khởi tạo buzzer
void initBuzzer();

// Beep ngắn 1 lần (xe vào/ra)
void buzzerBeep();

// Beep 2 lần nhanh (RFID OK)
void buzzerDoubleBeep();

// Beep dài (RFID bị từ chối)
void buzzerLongBeep();

// Bật/tắt báo động cháy (kêu liên tục)
void buzzerFireAlarm(bool on);

// Gọi trong loop() để xử lý báo động liên tục
void handleBuzzerLoop();

#endif
