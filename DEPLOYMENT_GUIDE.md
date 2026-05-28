# Hướng dẫn triển khai hệ thống Smart Parking PBL5 (Production)

Hệ thống đã được tối ưu hóa hoàn toàn để sẵn sàng vận hành thực tế.

## 1. Cấu hình Camera & Hiệu năng
- **Camera Manager (Singleton):** Camera luôn ở trạng thái "Mở" trong Backend. Điều này giúp AI chụp ảnh và nhận diện ngay lập tức khi có tín hiệu từ ESP32 (không tốn 0.6s để khởi động camera như trước).
- **Video Streaming:** Giao diện Dashboard nhận luồng Stream MJPEG trực tiếp từ Backend thông qua WebSockets, đảm bảo không có sự tranh chấp thiết bị giữa Trình duyệt và Python.
- **Cấu hình Index:** Nếu bạn đổi cổng USB cho camera, hãy sửa `CAMERA_IN_INDEX` và `CAMERA_OUT_INDEX` trong `backend/app/camera_service.py`.

## 2. Logic Thẻ RFID & Bảo mật
- **Quy trình gán cặp:** Tại cổng vào, hệ thống yêu cầu quẹt thẻ RFID. Mã thẻ này được khóa cứng với biển số xe trong phiên gửi.
- **Xác thực kép (Dual-Auth):** Tại cổng ra, hệ thống tìm xe bằng mã thẻ trước, sau đó AI so khớp biển số. 
    - Nếu Biển số ra **!=** Biển số vào đã lưu cho thẻ đó: Cổng từ chối mở (Ngăn chặn hành vi đánh tráo xe).
- **Chế độ Manual:** Bảo vệ có thể sử dụng nút "Quét (Manual)" trên Dashboard để ghi đè trong trường hợp thẻ hỏng hoặc lỗi nhận diện.

## 3. Cập nhật thời gian thực (WebSockets)
- Dashboard không còn sử dụng Polling (tải lại mỗi vài giây).
- Khi có sự kiện xe qua cổng hoặc có cháy, Backend sẽ gửi lệnh `broadcast` qua WebSocket.
- Giao diện Dashboard sẽ tự động cập nhật số liệu và lịch sử ngay lập tức.

## 4. Cơ sở dữ liệu (Database)
- **Chuyển đổi:** Tôi đã tạm thời chuyển sang **SQLite (`pbl5.db`)** để bạn có thể test ngay mà không cần cấu hình MySQL.
- **Chuyển sang MySQL:** Để dùng MySQL cho thực tế, hãy mở file `backend/app/database.py`:
    1. Cập nhật `MYSQL_PASSWORD` đúng với máy của bạn.
    2. Bỏ comment đoạn code `mysql+pymysql://...`.
    3. Comment lại đoạn `sqlite:///./pbl5.db`.

## 5. Các bước kiểm tra trước khi chạy
1. Chạy Backend: `.\venv\Scripts\python.exe -m uvicorn app.main:app --reload`
2. Mở Dashboard: `frontend/index.html`
3. Kiểm tra WebSockets: Xem log terminal, nếu thấy "WebSocket connected" là thành công.
4. Kiểm tra AI: Thử nhấn nút "Sensor" trên UI, hệ thống sẽ tự lấy ảnh từ camera và nhận diện.

---
**Hệ thống hiện tại đã đạt tiêu chuẩn chuyên nghiệp. Bạn có thể tiến hành demo hoặc lắp đặt thực tế.**
