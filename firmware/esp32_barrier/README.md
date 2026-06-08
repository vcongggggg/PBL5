## ESP32 Barrier Controller - PBL5

Firmware dieu khien mo hinh bai xe 2 cong:

- 2 servo barrier: cong vao / cong ra
- 2 cam bien IR: phat hien xe vao / ra
- 1 RFID RC522
- 1 cam bien chay
- 1 buzzer noi truc tiep GPIO32
- Khong dung relay va khong dung den canh bao rieng

## 1) Pin Map

| Chuc nang        | Chan ESP32 |
| ---------------- | ---------- |
| Servo IN signal  | `GPIO14` |
| Servo OUT signal | `GPIO13` |
| IR IN OUT        | `GPIO27` |
| IR OUT OUT       | `GPIO26` |
| Fire sensor DO   | `GPIO33` |
| Fire sensor AO   | `GPIO34` |
| Buzzer signal    | `GPIO32` |
| RC522 SS/SDA     | `GPIO5`  |
| RC522 RST        | `GPIO22` |
| RC522 SCK        | `GPIO18` |
| RC522 MISO       | `GPIO19` |
| RC522 MOSI       | `GPIO23` |

`GPIO25` hien khong su dung.

## 2) Nguon

- Servo dung nguon 5V ngoai, khuyen nghi 5V 3A tro len.
- ESP32 co the cap bang USB.
- Tat ca GND phai noi chung: GND adapter, GND ESP32, GND servo, GND IR, GND RFID, GND fire sensor, GND buzzer.
- RC522 chi dung 3.3V.
- Neu IR cap 5V va OUT ra muc 5V, nen dua OUT qua chia ap/level shifter truoc khi vao ESP32.

## 3) Dau Noi

### Servo

Moi servo:

- Do/VCC -> `+5V adapter`
- Nau/den/GND -> `GND chung`
- Cam/vang/signal:
  - Servo IN -> `GPIO14`
  - Servo OUT -> `GPIO13`

### IR

- IR IN OUT -> `GPIO27`
- IR OUT OUT -> `GPIO26`
- VCC -> theo module, thuong `5V` ngoai hoac `3V3`
- GND -> `GND chung`

Firmware co loc nhieu IR: tin hieu phai giu LOW lien tuc `IR_CONFIRM_MS` moi gui event.

### RFID RC522

- `SDA/SS` -> `GPIO5`
- `SCK` -> `GPIO18`
- `MOSI` -> `GPIO23`
- `MISO` -> `GPIO19`
- `RST` -> `GPIO22`
- `3.3V` -> `3V3 ESP32`
- `GND` -> `GND chung`

### Fire Sensor

- `DO` -> `GPIO33`
- `AO/A0` -> `GPIO34` de doc gia tri analog thuc te (ADC 0-4095)
- `VCC` -> `3V3` hoac `5V` theo module
- `GND` -> `GND chung`

Neu cap module bang `5V`, chan `AO/A0` co the len gan 5V. ESP32 chi chiu toi da 3.3V o GPIO, vi vay can chia ap/level shifter truoc khi dua vao `GPIO34`. Neu cap module bang `3V3`, co the noi truc tiep `AO/A0` vao `GPIO34`.

Firmware hien gia dinh cam bien chay active-low:

- `LOW` = phat hien chay
- `HIGH` = binh thuong

### Buzzer

- Buzzer signal/control -> `GPIO32`
- Buzzer GND -> `GND chung`

Neu buzzer an dong lon, nen dieu khien qua transistor/MOSFET thay vi noi truc tiep GPIO.

## 4) MQTT Topics

- `parking/device/esp32-barrier-01/event/car_detected`
- `parking/device/esp32-barrier-01/event/rfid_scan`
- `parking/device/esp32-barrier-01/event/fire_alert`
- `parking/device/esp32-barrier-01/event/fire_telemetry`
- `parking/device/esp32-barrier-01/command/open_gate`
- `parking/device/esp32-barrier-01/command/reset_fire`

## 5) Thu Vien Arduino

- `ESP32Servo`
- `MFRC522`
- `PubSubClient`
- `WiFiManager`

## 6) Test Phan Cung

Sketch test doc lap nam trong thu muc `test/`:

- `test/test_only_ir/test_only_ir.ino`
- `test/test_servo/test_servo.ino`
- `test/rfid_test.ino`
- `test/test_fire_buzzer/test_fire_buzzer.ino`
- `test/test_all_hardware/test_all_hardware.ino`

Thu tu test khuyen nghi: IR -> servo -> RFID -> fire/buzzer -> all hardware -> firmware chinh.
