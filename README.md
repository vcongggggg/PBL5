## PBL5 – Hệ thống bãi gửi xe thông minh

Repo này chứa mã nguồn cho:

- **Firmware ESP32** điều khiển barrier.
- **Backend FastAPI** xử lý logic bãi xe, giao tiếp với ESP32 và frontend.
- **Frontend Web** đơn giản để xem dashboard và quản lý xe vé tháng.

### 1. Cấu trúc thư mục

- `firmware/esp32_barrier/`
  - `esp32_barrier.ino`: code Arduino cho ESP32.
  - `README.md`: hướng dẫn phần vi điều khiển.
- `backend/`
  - `app/`
    - `main.py`: FastAPI app, API cho ESP32 và frontend.
    - `models.py`: SQLAlchemy models.
    - `schemas.py`: Pydantic schemas (request/response).
    - `database.py`: cấu hình kết nối DB.
  - `requirements.txt`: thư viện Python cần cài.
- `frontend/`
  - `index.html`: giao diện dashboard + quản lý xe (HTML + JS thuần gọi API).

### 2. Chạy backend FastAPI (dùng MySQL)

Yêu cầu Python 3.10+.

1. Tạo database MySQL (ví dụ `pbl5`) và một user có quyền truy cập.

2. Sửa thông tin kết nối trong `backend/app/database.py`:

```python
MYSQL_USER = "root"
MYSQL_PASSWORD = "password"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_DB = "pbl5"
```

3. Cài thư viện và chạy server:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Sau khi chạy:

- Kiểm tra health: `http://localhost:8000/health`
- Tài liệu API: `http://localhost:8000/docs`

### 3. Chạy frontend web (tĩnh)

Có thể mở trực tiếp file `frontend/index.html` bằng trình duyệt, hoặc dùng server tĩnh:

```bash
cd frontend
python -m http.server 5173
```

Sau đó mở `http://localhost:5173/` trong trình duyệt.  
Đảm bảo backend FastAPI đang chạy tại `http://localhost:8000`. Nếu đổi port/host, hãy sửa hằng số `API_BASE` trong `frontend/index.html`.

### 4. Kết nối với ESP32

- ESP32 gọi tới các endpoint:
  - `POST /api/esp/events`
  - `POST /api/esp/manual-open`
- Firmware mẫu hiện đang **giả lập biển số** để test luồng end-to-end.  
Khi AI (YOLO + OCR) hoàn thiện, backend sẽ được cập nhật để nhận ảnh, nhận diện biển số thật và cập nhật logic tính tiền / vé tháng.

