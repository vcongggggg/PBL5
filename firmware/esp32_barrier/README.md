## ESP32 Barrier Controller - PBL5

**Mục tiêu**: Điều khiển barrier bãi xe bằng ESP32, cảm biến IR, Servo MG996R và LCD 20x4, giao tiếp với backend FastAPI.

### 1. Phần cứng

- **ESP32 DevKit V1**
- **Servo MG996R** (nguồn riêng 5–6V khuyến nghị)
- **Cảm biến IR** E18-D80NK (ngõ ra digital)
- **LCD 20x4 I2C** (thường địa chỉ `0x27` hoặc `0x3F`)
- **Nút nhấn** mở cổng cưỡng bách

Gợi ý nối chân (có thể thay nhưng phải sửa trong code `esp32_barrier.ino`):

- IR OUT → GPIO `27`
- Servo signal → GPIO `14`
- Nút nhấn → GPIO `26` (kiểu `INPUT_PULLUP`, nhấn = LOW)
- LCD SDA → GPIO `21`, SCL → GPIO `22`

### 2. Thư viện Arduino cần cài

Trong Arduino IDE:

- `ESP32Servo`
- `LiquidCrystal_I2C` (loại hỗ trợ ESP32, có thể là bản của "Marco Schwartz" hoặc tương đương)

### 3. Cấu hình trong code

Mở file `esp32_barrier.ino` và chỉnh:

- `WIFI_SSID`, `WIFI_PASS`: tên và mật khẩu Wi‑Fi chung với server backend.
- `BACKEND_URL_EVENT`: URL API nhận sự kiện xe đến, ví dụ  
  `http://192.168.1.100:8000/api/esp/events`
- `BACKEND_URL_MANUAL_OPEN`: URL API log mở cổng cưỡng bách, ví dụ  
  `http://192.168.1.100:8000/api/esp/manual-open`
- `DEVICE_ID`: chuỗi định danh cổng, ví dụ `"gate-1"`.

Backend FastAPI cần trả JSON dạng:

```json
{
  "action": "open",
  "plate": "51F-123.45",
  "vehicle_type": "monthly",
  "message": "Xe ve thang, con han"
}
```

Trong phiên bản hiện tại, firmware chỉ kiểm tra trường `"action"` chứa `"open"` để quyết định mở/đóng barrier.

### 4. Luồng hoạt động

1. ESP32 khởi động, kết nối Wi‑Fi, hiển thị "Waiting for car" trên LCD.
2. Khi cảm biến IR phát hiện xe (cạnh lên từ LOW → HIGH), ESP32:
   - Gửi `POST` đến `BACKEND_URL_EVENT` với JSON gồm `device_id`, `event_type = car_detected`, `direction = in`.
   - Đợi phản hồi:
     - Nếu trả về `"action": "open"` → mở barrier, hiển thị thông báo trên LCD.
     - Ngược lại → hiển thị "Access denied" và giữ barrier đóng.
3. Nút nhấn mở cưỡng bách:
   - Khi nhấn, ESP32 mở barrier, hiển thị "Manual OPEN" và gửi `POST` lên `BACKEND_URL_MANUAL_OPEN`.
4. Sau `AUTO_CLOSE_MS` (mặc định 8 giây), barrier tự động đóng lại và LCD trở về "Waiting car".

### 5. Hướng dẫn lắp mạch thật (chi tiết)

#### 5.1. Chuẩn bị linh kiện

| Linh kiện | Số lượng | Ghi chú |
|-----------|----------|---------|
| ESP32 DevKit V1 | 1 | Đã có |
| Cảm biến IR / Photoelectric (E18-D80NK hoặc tương đương) | 1 | Đã có |
| Servo MG996R | 1 | Cần mua – dùng nguồn 5–6V riêng |
| LCD 20x4 I2C (module PCF8574) | 1 | Cần mua – địa chỉ 0x27 hoặc 0x3F |
| Nút nhấn | 1 | Cần mua – loại thường mở (NO) |
| Dây jumper (đực–đực, đực–cái) | 1 bộ | Đã có |
| Cáp USB Micro | 1 | Đã có |
| Nguồn 5V/2A (adapter) | 1 | Khuyến nghị – cấp riêng cho Servo nếu dòng lớn |

#### 5.2. Sơ đồ nối dây

```
                    ESP32 DevKit V1
                    ┌─────────────────┐
                    │                 │
    IR OUT ─────────┤ GPIO 27         │
                    │                 │
    Servo signal ───┤ GPIO 14         │
                    │                 │
    Nút nhấn ───────┤ GPIO 26         │  (một chân nút → GND)
                    │                 │
    LCD SDA ────────┤ GPIO 21         │
    LCD SCL ────────┤ GPIO 22         │
                    │                 │
    GND ────────────┤ GND             │
    3V3/5V ─────────┤ 3V3 hoặc 5V     │  (cho LCD, IR, nút)
                    └─────────────────┘
```

#### 5.3. Nối từng linh kiện

**Cảm biến IR / Photoelectric (phát hiện xe):**

- Cảm biến thường có 3 dây: **VCC** (nâu/đỏ), **GND** (xanh dương), **OUT** (đen/xanh lá).
- Nối:
  - VCC → **3V3** hoặc **5V** (tùy datasheet cảm biến)
  - GND → **GND**
  - OUT → **GPIO 27**

**Servo MG996R:**

- 3 dây: **Nâu** = GND, **Đỏ** = VCC (5–6V), **Cam/Vàng** = Signal.
- Nối:
  - Nâu → **GND** (nên dùng nguồn ngoài nếu adapter 5V đủ mạnh)
  - Đỏ → **5V** (hoặc nguồn ngoài 5–6V)
  - Cam/Vàng → **GPIO 14**

**LCD 20x4 I2C:**

- Module I2C có 4 chân: **VCC**, **GND**, **SDA**, **SCL**.
- Nối:
  - VCC → **5V** hoặc **3V3**
  - GND → **GND**
  - SDA → **GPIO 21**
  - SCL → **GPIO 22**

**Nút nhấn mở cổng cưỡng bách:**

- Nối 1 chân nút → **GPIO 26**, chân còn lại → **GND**.
- Code dùng `INPUT_PULLUP` nên không cần điện trở kéo lên.

#### 5.4. Lắp trên breadboard (từng bước)

**Cấu trúc breadboard cơ bản:**

- Hai **thanh dọc** hai bên: dùng làm **+** (đỏ) và **−** (xanh) – nối nguồn vào đây.
- Các **hàng ngang** ở giữa: mỗi hàng 5 lỗ thông nhau (a–e và f–j tách đôi ở rãnh giữa).
- **Rãnh giữa**: chia đôi breadboard, ESP32 cắm ngang qua rãnh.

**Bước 1 – Cấp nguồn cho breadboard**

- Dùng dây jumper: **5V USB** (hoặc adapter) → một lỗ trên thanh **+** (đỏ).
- **GND** → một lỗ trên thanh **−** (xanh).
- Nối thêm dây từ thanh **+** bên trái sang thanh **+** bên phải, thanh **−** tương tự (nếu breadboard chưa nối sẵn).

**Bước 2 – Đặt ESP32**

- Cắm ESP32 **ngang** qua rãnh giữa, sao cho hai hàng chân nằm ở hai bên rãnh.
- Đảm bảo chân **3V3**, **GND**, **5V**, **GPIO 14, 21, 22, 26, 27** dễ tiếp cận.

**Bước 3 – Nối GND và nguồn chung**

- Dây từ **GND** ESP32 → thanh **−** breadboard.
- Dây từ **3V3** hoặc **5V** ESP32 → thanh **+** breadboard (tùy linh kiện dùng 3V3 hay 5V).

**Bước 4 – Cảm biến IR**

- Cắm 3 chân IR vào 3 lỗ cùng hàng (hoặc 3 hàng liền kề).
- Dây **VCC** IR → thanh **+**.
- Dây **GND** IR → thanh **−**.
- Dây **OUT** IR → dây jumper → **GPIO 27** ESP32.

**Bước 5 – Servo**

- Servo thường cắm ngoài breadboard (dây dài).
- **Nâu (GND)** → thanh **−** breadboard.
- **Đỏ (VCC)** → thanh **+** (5V) hoặc nguồn ngoài.
- **Cam (Signal)** → dây jumper → **GPIO 14** ESP32.

**Bước 6 – LCD I2C**

- Cắm 4 chân LCD vào breadboard (một hàng 4 lỗ).
- **VCC** → thanh **+**
- **GND** → thanh **−**
- **SDA** → dây jumper → **GPIO 21** ESP32
- **SCL** → dây jumper → **GPIO 22** ESP32

**Bước 7 – Nút nhấn**

- Cắm nút **ngang qua rãnh giữa** (2 chân mỗi bên).
- Một chân nút → dây jumper → **GPIO 26** ESP32.
- Chân đối diện (cùng bên nút) → thanh **−** (GND).

**Sơ đồ vị trí (minh họa):**

```
     Breadboard (nhìn từ trên)
     + rail ─────────────────────────  (đỏ, 5V/3V3)
     − rail ─────────────────────────  (xanh, GND)
     ┌───┬───┬───┬───┬───┐
     │ a │ b │ c │ d │ e │  ← hàng thông nhau
     ├───┼───┼───┼───┼───┤
     │   │   │   │   │   │
     ╞═══╪═══╪═══╪═══╪═══╡  ← rãnh giữa, ESP32 cắm ngang
     │   │   │   │   │   │
     ├───┼───┼───┼───┼───┤
     │ f │ g │ h │ i │ j │
     └───┴───┴───┴───┴───┘

     ESP32:  [====|====]  cắm ngang qua rãnh
             chân trái   chân phải
```

**Lưu ý breadboard:**

- Mỗi hàng 5 lỗ **thông nhau** – các chân cùng hàng được nối.
- Hai bên rãnh giữa **không thông** – dùng để cắm IC/board 2 hàng chân.
- Dùng dây **ngắn**, tránh rối; màu dây: đỏ = nguồn, đen = GND, các màu khác = tín hiệu.

#### 5.5. Lưu ý khi lắp

1. **Tắt nguồn** trước khi nối/ngắt dây.
2. **Kiểm tra cực** VCC/GND trước khi cấp điện.
3. **Servo** tiêu thụ dòng lớn khi quay – nếu ESP32 bị reset, dùng nguồn 5V ngoài cho Servo.
4. **Cảm biến IR**: một số loại OUT = HIGH khi có vật, một số = LOW. Nếu ngược logic, đổi điều kiện trong code (`digitalRead(IR_PIN) == LOW` thay vì `== HIGH`).
5. **LCD không sáng**: thử đổi địa chỉ I2C trong code từ `0x27` sang `0x3F` (hoặc dùng sketch quét địa chỉ I2C).

#### 5.6. Thứ tự test an toàn

1. Chỉ nối **ESP32 + USB** → nạp code, mở Serial Monitor xem Wi‑Fi kết nối.
2. Thêm **cảm biến IR** → in trạng thái ra Serial khi che/không che.
3. Thêm **Servo** → test `openGate()` / `closeGate()` trong code.
4. Thêm **LCD** → test hiển thị chữ.
5. Thêm **nút nhấn** → test manual open.
6. Kết nối backend (sửa `BACKEND_URL_*`), test full luồng.

---

### 6. Gợi ý test

- Test riêng từng phần:
  - Servo: chạy hàm `openGate()` / `closeGate()` trong code mẫu đơn giản.
  - Cảm biến IR: in trạng thái `digitalRead(IR_PIN)` ra Serial.
  - LCD: thử code hello world của thư viện.
- Khi backend chưa hoàn thành:
  - Có thể dùng một server giả (Postman Mock / FastAPI tạm) trả cứng JSON `"action":"open"` để test cơ khí.

