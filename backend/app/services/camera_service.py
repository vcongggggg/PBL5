import os
# Tắt log lỗi từ core C++ của OpenCV (Phải đặt trước khi import cv2)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["PYTHONWARNINGS"] = "ignore"

# Tải cấu hình từ file .env nếu có
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import cv2
import threading
import logging
import time
import subprocess

logger = logging.getLogger("uvicorn")

# ============ CẤU HÌNH CAMERA ============
# Tên camera cố định cho làn vào và làn ra (Có thể cấu hình từ file .env)
CAMERA_IN_NAME = os.getenv("CAMERA_IN_NAME", "DV20 USB CAMERA")
CAMERA_OUT_NAME = os.getenv("CAMERA_OUT_NAME", "GENERAL - UVC")

# Chỉ số dự phòng mặc định nếu tự động nhận diện thất bại (ban đầu đặt là None để phát hiện camera chính xác)
CAMERA_IN_INDEX = None
CAMERA_OUT_INDEX = None

# Cho phép ghi đè index camera qua biến môi trường để cấu hình linh hoạt
env_in = os.getenv("CAMERA_IN_INDEX")
env_out = os.getenv("CAMERA_OUT_INDEX")
USE_AUTO_DETECT = True  # Bật tự động nhận diện camera qua tên theo mặc định

if env_in is not None and env_out is not None:
    try:
        CAMERA_IN_INDEX = int(env_in)
        CAMERA_OUT_INDEX = int(env_out)
        USE_AUTO_DETECT = False
        logger.info(f"Đã nhận cấu hình camera từ biến môi trường: IN={CAMERA_IN_INDEX}, OUT={CAMERA_OUT_INDEX}")
    except ValueError:
        pass



def auto_detect_camera_indices():
    """
    Tự động tìm chỉ số camera làn vào và làn ra dựa trên tên camera cố định.
    Sử dụng thư viện cv2_enumerate_cameras để khớp tên với OpenCV index.
    """
    global CAMERA_IN_INDEX, CAMERA_OUT_INDEX

    if not USE_AUTO_DETECT:
        logger.info("Tự động nhận diện camera bị tắt. Sử dụng chỉ số cố định hoặc từ môi trường.")
        return

    logger.info("Đang tự động nhận diện chỉ số camera theo tên...")
    try:
        from cv2_enumerate_cameras import enumerate_cameras
        cameras = list(enumerate_cameras())
        logger.info("Danh sách camera phát hiện được bởi hệ thống:")
        for c in cameras:
            logger.info(f" - Index: {c.index}, Tên: '{c.name}', Backend: {c.backend}")

        found_in = None
        found_out = None

        # DirectShow (backend = 0 hoặc c.index trong khoảng 700-799) chạy ổn định hơn trên Windows.
        # Chúng ta sẽ ưu tiên chọn các camera có DirectShow backend (700-799), 
        # nhưng nếu không tìm thấy thì chấp nhận bất kỳ backend nào (như MSMF 1400-1499).
        for c in cameras:
            name_upper = c.name.strip().upper()
            target_in_upper = CAMERA_IN_NAME.strip().upper()
            target_out_upper = CAMERA_OUT_NAME.strip().upper()

            if target_in_upper in name_upper:
                # Ưu tiên DirectShow (700 <= c.index < 800) hoặc nếu chưa gán chỉ số nào
                if found_in is None or (700 <= c.index < 800):
                    found_in = c.index
            elif target_out_upper in name_upper:
                # Ưu tiên DirectShow (700 <= c.index < 800) hoặc nếu chưa gán chỉ số nào
                if found_out is None or (700 <= c.index < 800):
                    found_out = c.index

        if found_in is not None:
            CAMERA_IN_INDEX = found_in
            logger.info(f"-> Đã gán thành công camera làn VÀO: '{CAMERA_IN_NAME}' -> Index: {CAMERA_IN_INDEX}")
        else:
            CAMERA_IN_INDEX = None
            logger.warning(f"-> Không tìm thấy camera làn VÀO với tên chứa '{CAMERA_IN_NAME}'. Màn hình cổng vào sẽ tắt.")

        if found_out is not None:
            CAMERA_OUT_INDEX = found_out
            logger.info(f"-> Đã gán thành công camera làn RA: '{CAMERA_OUT_NAME}' -> Index: {CAMERA_OUT_INDEX}")
        else:
            CAMERA_OUT_INDEX = None
            logger.warning(f"-> Không tìm thấy camera làn RA với tên chứa '{CAMERA_OUT_NAME}'. Màn hình cổng ra sẽ tắt.")

    except Exception as e:
        logger.error(f"Lỗi khi tự động nhận diện camera qua tên: {e}.")


# ============ CHẠY AUTO-DETECT KHI KHỞI ĐỘNG ============
auto_detect_camera_indices()


class CameraManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance.cameras = {}        # {"entry": VideoCapture, "exit": VideoCapture}
                cls._instance.opened_indices = {} # {"entry": int/None, "exit": int/None}
                cls._instance.last_frames = {}    # {"entry": (timestamp, bytes), "exit": (timestamp, bytes)}
                cls._instance.capture_locks = {}  # {"entry": Lock, "exit": Lock}
                cls._instance.failed_cameras = {} # {"entry": last_fail_time, "exit": last_fail_time}
                cls._instance.is_running = True
                cls._instance.threads = {}        # {"entry": Thread, "exit": Thread}
                cls._instance.thread_locks = threading.Lock()
        return cls._instance

    def _get_capture_lock(self, gate_type):
        if gate_type not in self.capture_locks:
            self.capture_locks[gate_type] = threading.Lock()
        return self.capture_locks[gate_type]

    def _resolve_index(self, gate_type):
        return CAMERA_IN_INDEX if gate_type == "entry" else CAMERA_OUT_INDEX

    def get_camera(self, gate_type):
        current_index = self._resolve_index(gate_type)

        # Neu camera da duoc mo nhung chi so mo truoc do khac voi chi so moi duoc detect (bi thay doi do cam/rut USB),
        # thi ta phai giai phong va dong camera cu de mo lai tren dung index moi.
        if gate_type in self.cameras:
            opened_index = self.opened_indices.get(gate_type)
            if opened_index != current_index:
                logger.info(f"Chi so camera lan {gate_type} thay doi tu {opened_index} sang {current_index}. Dang lam moi ket noi...")
                with self._get_capture_lock(gate_type):
                    try:
                        self.cameras[gate_type].release()
                    except Exception:
                        pass
                    del self.cameras[gate_type]
                    if gate_type in self.opened_indices:
                        del self.opened_indices[gate_type]

        if gate_type not in self.cameras:
            now = time.time()
            if gate_type in self.failed_cameras and now - self.failed_cameras[gate_type] < 3:
                return None

            index = current_index
            if index is None:
                # Nếu chưa gán index, thử quét lại thiết bị
                auto_detect_camera_indices()
                index = self._resolve_index(gate_type)
                if index is None:
                    self.failed_cameras[gate_type] = now
                    return None

            logger.info(f"Dang mo camera cho lan {gate_type} bang chi so {index}...")
            
            # Tren Windows, neu index >= 700 (da ma hoa backend tu cv2_enumerate_cameras nhu 700, 1400...)
            # thi ta truyen thang index vao cv2.VideoCapture(index) ma khong kem theo cv2.CAP_DSHOW.
            # Neu index < 700 (index mac dinh nhu 0, 1, 2...), ta ep dung CAP_DSHOW de tranh MSMF timeout 18 giay.
            if index >= 700:
                cap = cv2.VideoCapture(index)
            else:
                cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

            if cap.isOpened():
                logger.info(f"Mo thanh cong camera cho lan {gate_type} (index {index})")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cameras[gate_type] = cap
                self.opened_indices[gate_type] = index
                if gate_type in self.failed_cameras:
                    del self.failed_cameras[gate_type]
            else:
                if gate_type not in self.failed_cameras:
                    logger.error(f"Khong mo duoc camera cho lan {gate_type} index {index}. Dang quet lai thiet bi USB...")
                # Khi gặp lỗi, tự động quét lại thiết bị USB ngoài để cập nhật index mới
                auto_detect_camera_indices()
                self.failed_cameras[gate_type] = now
                return None
        return self.cameras[gate_type]

    def start_camera_thread(self, gate_type):
        with self.thread_locks:
            if gate_type in self.threads and self.threads[gate_type].is_alive():
                return
            
            t = threading.Thread(target=self._camera_loop, args=(gate_type,), daemon=True)
            self.threads[gate_type] = t
            t.start()
            logger.info(f"Khoi chay background thread cho camera lan {gate_type}")

    def _camera_loop(self, gate_type):
        logger.info(f"Camera background loop bat dau cho lan {gate_type}")
        while self.is_running:
            cap = self.get_camera(gate_type)
            if cap is None:
                time.sleep(2.0)
                continue
            
            try:
                ret, frame = cap.read()
                if not ret:
                    logger.error(f"Loi doc frame tu camera {gate_type} trong background thread. Dang tu dong quet lai...")
                    with self._get_capture_lock(gate_type):
                        if gate_type in self.cameras:
                            try:
                                self.cameras[gate_type].release()
                            except Exception:
                                pass
                            del self.cameras[gate_type]
                    # Khi mất kết nối hoặc lỗi đọc, tự động quét lại cổng USB để cập nhật chỉ số mới
                    auto_detect_camera_indices()
                    self.failed_cameras[gate_type] = time.time()
                    time.sleep(2.0)
                    continue

                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                
                with self._get_capture_lock(gate_type):
                    self.last_frames[gate_type] = (time.time(), frame_bytes)
                
                time.sleep(0.04)  # ~25 FPS
            except Exception as e:
                logger.error(f"Loi trong camera loop {gate_type}: {e}")
                time.sleep(2.0)

    def capture(self, gate_type: str):
        if not self.is_running:
            return None

        if gate_type not in ["entry", "exit"]:
            return None

        if gate_type not in self.threads or not self.threads[gate_type].is_alive():
            self.start_camera_thread(gate_type)

        now = time.time()
        timeout = 2.0
        start_wait = time.time()
        while gate_type not in self.last_frames and (time.time() - start_wait < timeout):
            time.sleep(0.01)

        if gate_type in self.last_frames:
            ts, frame_bytes = self.last_frames[gate_type]
            if now - ts > 3.0:
                return None
            return frame_bytes
        return None

    def release_all(self):
        self.is_running = False
        for gate_type, thread in list(self.threads.items()):
            if thread.is_alive():
                thread.join(timeout=1.0)
        self.threads = {}
        
        for gate_type, cap in list(self.cameras.items()):
            try:
                cap.release()
            except Exception:
                pass
        self.cameras = {}
        self.last_frames = {}
        logger.info("Released all cameras and stopped background threads.")


camera_manager = CameraManager()


def capture_image(gate_type: str):
    return camera_manager.capture(gate_type)


async def gen_frames(gate_type: str):
    import asyncio
    while True:
        frame_bytes = camera_manager.capture(gate_type)
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.05)
