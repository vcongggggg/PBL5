## ESP32 Barrier Controller - PBL5 (Hardware v2)

**Mục tiêu:** điều khiển mô hình bãi xe 2 cổng với:

- 2 servo (Gate IN / Gate OUT)
- 2 cảm biến IR (phát hiện xe vào / ra)
- 1 RFID RC522
- 1 cảm biến cháy
- 1 relay 2 kênh (còi/đèn cảnh báo)

## 1) Pin map chuẩn theo firmware mới

| Chức năng | Chân ESP32 |
|---|---|
| Servo IN signal | `GPIO14` |
| Servo OUT signal | `GPIO13` |
| IR IN | `GPIO27` |
| IR OUT | `GPIO26` |
| Fire sensor DO | `GPIO33` |
| Relay CH1 | `GPIO32` |
| Relay CH2 | `GPIO25` |
| RC522 SS (SDA) | `GPIO5` |
| RC522 RST | `GPIO22` |
| RC522 SCK | `GPIO18` |
| RC522 MISO | `GPIO19` |
| RC522 MOSI | `GPIO23` |

## 2) Sơ đồ nguồn (quan trọng)

### Nguồn khuyến nghị

- Adapter ngoài `5V 3A` trở lên (khuyến nghị `5V 5A` nếu 2 servo tải nặng)
- ESP32 có thể vẫn cấp bằng USB từ máy tính

### Quy tắc bắt buộc

1. **2 servo lấy nguồn từ adapter 5V ngoài** (không lấy từ 3V3).
2. **GND tất cả phải nối chung mass**:
   - GND adapter
   - GND ESP32
   - GND servo
   - GND IR/RFID/fire/relay

## 3) Nối dây từng nhóm linh kiện

### 3.1 Servo IN / Servo OUT

Mỗi servo MG996R:

- Dây **đỏ** → `+5V adapter`
- Dây **nâu/đen** → `GND adapter`
- Dây **cam/vàng**:
  - Servo IN → `GPIO14`
  - Servo OUT → `GPIO13`

### 3.2 Cảm biến IR

- IR IN OUT → `GPIO27`
- IR OUT OUT → `GPIO26`
- VCC → `3V3` hoặc `5V` (theo module bạn dùng)
- GND → `GND`

### 3.3 RFID RC522 (SPI)

- `SDA(SS)` → `GPIO5`
- `SCK` → `GPIO18`
- `MOSI` → `GPIO23`
- `MISO` → `GPIO19`
- `RST` → `GPIO22`
- `3.3V` → `3V3 ESP32` (**không dùng 5V cho RC522**)
- `GND` → `GND`

### 3.4 Cảm biến cháy

- `DO` → `GPIO33`
- `VCC` → `3V3` hoặc `5V` (theo module)
- `GND` → `GND`

### 3.5 Relay 2 kênh

- `IN1` → `GPIO32`
- `IN2` → `GPIO25`
- `VCC` → `5V`
- `GND` → `GND`

Phần tải của relay:

- CH1: dùng cho còi (COM-NO)
- CH2: dùng cho đèn cảnh báo (COM-NO)

## 4) API backend firmware sẽ gọi

- `POST /api/esp/events` (IR IN/OUT)
- `POST /api/esp/rfid` (UID thẻ)
- `POST /api/esp/fire-alert` (cảnh báo cháy)

## 5) Checklist test từng bước

1. Test Wi-Fi + gọi API đơn giản.
2. Test từng IR (IN và OUT) xem có gửi event đúng direction.
3. Test từng servo riêng (IN rồi OUT).
4. Test RC522 đọc UID qua Serial.
5. Test fire sensor kích hoạt relay và gửi `/api/esp/fire-alert`.
6. Test full-flow: IR/UID hợp lệ -> mở đúng cổng -> tự đóng sau timeout.

## 6) Thư viện Arduino cần cài

- `ESP32Servo`
- `MFRC522`

## 7) Cấu trúc code kiểu mới (modular)

Firmware đã tách theo kiểu C++ nhiều file:

- `esp32_barrier.ino`: chỉ giữ `setup()` và `loop()`
- `config.h`: toàn bộ cấu hình Wi-Fi, URL backend, pin map
- `network_service.h/.cpp`: kết nối Wi-Fi
- `gate_controller.h/.cpp`: điều khiển 2 servo + relay
- `rfid_service.h/.cpp`: đọc UID từ RC522
- `api_client.h/.cpp`: gọi API backend (`/events`, `/rfid`, `/fire-alert`)

Bạn vẫn nạp bình thường như Arduino sketch, IDE sẽ tự build tất cả file trong cùng thư mục.


