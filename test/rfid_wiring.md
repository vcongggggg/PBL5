# Hướng dẫn đấu nối RFID-RC522 với ESP32

Mô-đun RFID-RC522 sử dụng giao tiếp SPI để kết nối với ESP32. Dưới đây là sơ đồ đấu nối dựa trên cấu hình trong mã nguồn của dự án.

> [!CAUTION]
> **RFID-RC522 chỉ hoạt động với điện áp 3.3V.** Cắm vào chân 5V có thể làm hỏng mô-đun ngay lập tức.

## Sơ đồ chân (Pinout)

| RFID-RC522 Pin | ESP32 Pin | Ghi chú |
| :--- | :--- | :--- |
| **VCC** | **3.3V** | Cấp nguồn 3.3V |
| **RST** | **GPIO 22** | Chân Reset |
| **GND** | **GND** | Chân đất |
| **IRQ** | *N/A* | Không sử dụng |
| **MISO** | **GPIO 19** | SPI MISO |
| **MOSI** | **GPIO 23** | SPI MOSI |
| **SCK** | **GPIO 18** | SPI Clock |
| **SDA (SS)** | **GPIO 5** | SPI Slave Select |

## Hình ảnh minh họa
Bạn có thể tham khảo sơ đồ chân thực tế trên board ESP32 DevKit V1. Đảm bảo các kết nối chắc chắn để tránh lỗi không nhận diện được mô-đun.

---
*Tài liệu này được tạo tự động để hỗ trợ kiểm thử phần cứng cho dự án PBL5.*
