# Cấu Trúc Kiến Trúc Backend Mới (Refactored)

Sau quá trình tái cấu trúc (refactor), file `app/main.py` khổng lồ (>600 dòng) đã được phân chia theo nguyên tắc "Separation of Concerns" (tách biệt trách nhiệm). Hệ thống hiện tại áp dụng kiến trúc **Router - Service - Core/State**, giúp code dễ bảo trì, dễ mở rộng và độc lập với nhau.

## 1. Cấu trúc thư mục hiện tại

```text
backend/
├── app/
│   ├── core/              # Chứa các utilities cốt lõi, constants, auth
│   │   ├── security.py
│   │   └── time_utils.py
│   ├── integrations/      # Các module giao tiếp với hệ thống bên ngoài (MQTT, AWS...)
│   │   └── mqtt_manager.py
│   ├── routers/           # Chứa toàn bộ các API Endpoints (FastAPI Routers)
│   │   ├── admin.py
│   │   ├── ai.py
│   │   ├── camera.py
│   │   ├── dashboard.py
│   │   ├── esp.py
│   │   ├── fire.py
│   │   ├── gate.py
│   │   ├── parking.py
│   │   └── ws.py
│   ├── services/          # Nơi chứa các Logic Nghiệp Vụ (Business Logic)
│   │   ├── ai_service.py
│   │   ├── camera_service.py
│   │   ├── config_service.py
│   │   ├── dashboard_service.py
│   │   ├── fire_service.py
│   │   ├── gate_logic.py
│   │   ├── parking_service.py
│   │   ├── plate_tracker.py
│   │   └── realtime.py
│   ├── state.py           # Quản lý các biến global state in-memory
│   └── main.py            # Entry point cực kỳ nhỏ gọn (~70 dòng), chỉ init app & gán routers
```

---

## 2. Nhiệm vụ của từng thành phần

### 2.1. `app/main.py`
- Là entry point của toàn bộ ứng dụng FastAPI.
- **Nhiệm vụ:**
  - Khởi tạo FastAPI app.
  - Setup Middleware (CORS).
  - Khởi tạo cơ sở dữ liệu (`models.Base.metadata.create_all`).
  - Gắn (include) tất cả các routers từ thư mục `routers/`.
  - Không chứa logic nghiệp vụ, MQTT processing hay WebSocket streaming.

### 2.2. `app/routers/` (Tầng API Endpoints)
Mỗi file đại diện cho một domain cụ thể. Các router chỉ làm nhiệm vụ tiếp nhận Request, kiểm tra tham số, gọi đến `services/` để xử lý logic, và trả về Response.
- **`admin.py`:** API dành cho quản trị viên (thêm/sửa/xoá thẻ, cấu hình hệ thống).
- **`camera.py` & `ai.py`:** API trả về video stream (`StreamingResponse`) từ camera, lấy hình ảnh AI, và crop biển số.
- **`dashboard.py`:** API cấp số liệu thống kê cho trang chủ.
- **`esp.py`:** API nội bộ để các thiết bị ESP32 (quét thẻ, đóng/mở cổng, báo cháy) giao tiếp thông qua HTTP (dự phòng cho MQTT).
- **`fire.py`:** API xử lý hệ thống báo cháy, ngắt báo cháy.
- **`gate.py`:** API xử lý mở cổng thủ công, cảm biến vòng từ (loop sensor) khi xe đi qua cổng.
- **`parking.py`:** API tra cứu thông tin lượt gửi xe, thanh toán.
- **`ws.py`:** API quản lý WebSocket để đẩy dữ liệu realtime về Frontend.

### 2.3. `app/services/` (Tầng Business Logic)
Nơi chứa toàn bộ logic xử lý phức tạp.
- **`gate_logic.py`:** Chứa hàm cốt lõi `handle_mqtt_event`, xử lý quy trình xe vào/ra, quy trình xác thực quẹt thẻ kết hợp AI nhận diện biển số (LPR).
- **`parking_service.py`:** Chứa các hàm tính tiền (`calculate_fee`), kiểm tra thẻ, lưu logs vào DB, đếm số lượng xe trong bãi và trạng thái bãi xe.
- **`fire_service.py`:** Logic tự động mở cổng khi có báo cháy, đánh dấu các cảnh báo cháy.
- **`dashboard_service.py`:** Truy vấn và tính toán doanh thu, lượt vào ra theo ngày.
- **`ai_service.py` & `camera_service.py` & `plate_tracker.py`:** Giao tiếp với model AI, chụp khung hình từ camera (RTSP hoặc USB), track biển số để tránh nhận diện trùng lặp.
- **`config_service.py`:** Đọc và cache các cấu hình hệ thống (như giá tiền, số lượng chỗ đỗ, ngưỡng cảnh báo) từ database.
- **`realtime.py`:** Tách logic WebSocket connection manager để đẩy message (thay vì gộp chung ở ws router).

### 2.4. `app/core/` & `app/state.py`
- **`state.py`:** Tập trung tất cả các biến Global State (chẳng hạn `_manual_gate_open_until`, `gate_locks`, `esp32_ip`, `_pending_rfid_scans`). Điều này tránh việc Circular Import và giúp các services độc lập truy xuất.
- **`core/time_utils.py`:** Quy chuẩn múi giờ (`get_vietnam_now()`), tiện cho việc maintain.
- **`core/security.py`:** Hàm `verify_api_key`.

---

## 3. Lợi ích của kiến trúc mới
1. **Dễ đọc (Readability):** File `main.py` không còn quá tải. Việc tìm kiếm logic mở cổng chỉ cần vào `gate_logic.py`.
2. **Loại bỏ Circular Import:** Bằng cách kéo các biến toàn cục ra file `state.py`, việc import chéo giữa main và services đã được giải quyết hoàn toàn.
3. **Mở rộng dễ dàng (Scalability):** Nếu muốn thêm một Module (Ví dụ: Thanh toán VNPay), chỉ việc thêm file `routers/vnpay.py` và `services/payment_service.py`.
4. **Sẵn sàng để Test:** Các logic trong `services/` đã nhận `db` dưới dạng tham số thay vì dùng Dependency Injection cứng của FastAPI. Điều này khiến quá trình viết Unit Test tương lai cực kỳ đơn giản (mock db).

*Tài liệu này được tạo tự động nhằm hỗ trợ các kỹ sư phần mềm tiếp quản và phát triển dễ dàng hơn.*
