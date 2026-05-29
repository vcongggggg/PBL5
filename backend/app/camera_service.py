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

logger = logging.getLogger(__name__)

# ============ CẤU HÌNH CAMERA ============
# Tên camera cố định cho làn vào và làn ra (Có thể cấu hình từ file .env)
CAMERA_IN_NAME = os.getenv("CAMERA_IN_NAME", "DV20 USB CAMERA")
CAMERA_OUT_NAME = os.getenv("CAMERA_OUT_NAME", "GENERAL - UVC")

# Chỉ số dự phòng mặc định nếu tự động nhận diện thất bại
CAMERA_IN_INDEX = 0
CAMERA_OUT_INDEX = 1

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
            logger.warning(f"-> Không tìm thấy camera làn VÀO với tên chứa '{CAMERA_IN_NAME}'. Sử dụng mặc định: {CAMERA_IN_INDEX}")

        if found_out is not None:
            CAMERA_OUT_INDEX = found_out
            logger.info(f"-> Đã gán thành công camera làn RA: '{CAMERA_OUT_NAME}' -> Index: {CAMERA_OUT_INDEX}")
        else:
            logger.warning(f"-> Không tìm thấy camera làn RA với tên chứa '{CAMERA_OUT_NAME}'. Sử dụng mặc định: {CAMERA_OUT_INDEX}")

    except Exception as e:
        logger.error(f"Lỗi khi tự động nhận diện camera qua tên: {e}. Sử dụng mặc định: IN={CAMERA_IN_INDEX}, OUT={CAMERA_OUT_INDEX}")


# ============ CHẠY AUTO-DETECT KHI KHỞI ĐỘNG ============
auto_detect_camera_indices()


class CameraManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance.cameras = {}
                cls._instance.last_frames = {}  # {index: (timestamp, bytes)}
                cls._instance.capture_locks = {}  # {index: Lock}
                cls._instance.failed_cameras = {}  # {index: last_fail_time}
                cls._instance.is_running = True  # Cờ để dừng luồng khi shutdown
                cls._instance.threads = {}  # {index: Thread}
                cls._instance.thread_locks = threading.Lock()
        return cls._instance

    def _get_capture_lock(self, index):
        if index not in self.capture_locks:
            self.capture_locks[index] = threading.Lock()
        return self.capture_locks[index]

    def get_camera(self, index):
        if index not in self.cameras:
            now = time.time()
            if index in self.failed_cameras and now - self.failed_cameras[index] < 10:
                return None

            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                logger.info(f"Successfully opened Camera {index}")
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cameras[index] = cap
                if index in self.failed_cameras:
                    del self.failed_cameras[index]
            else:
                if index not in self.failed_cameras:
                    logger.error(f"Failed to open Camera {index} (Will retry silently every 10s)")
                self.failed_cameras[index] = now
                return None
        return self.cameras[index]

    def start_camera_thread(self, index):
        with self.thread_locks:
            if index in self.threads and self.threads[index].is_alive():
                return
            
            t = threading.Thread(target=self._camera_loop, args=(index,), daemon=True)
            self.threads[index] = t
            t.start()
            logger.info(f"Started background thread for Camera {index}")

    def _camera_loop(self, index):
        logger.info(f"Camera background loop started for index {index}")
        while self.is_running:
            cap = self.get_camera(index)
            if cap is None:
                time.sleep(1.0)
                continue
            
            try:
                ret, frame = cap.read()
                if not ret:
                    logger.error(f"Failed to read frame from Camera {index} in background thread")
                    with self._get_capture_lock(index):
                        if index in self.cameras:
                            try:
                                self.cameras[index].release()
                            except Exception:
                                pass
                            del self.cameras[index]
                    self.failed_cameras[index] = time.time()
                    time.sleep(2.0)
                    continue

                _, buffer = cv2.imencode('.jpg', frame)
                frame_bytes = buffer.tobytes()
                
                with self._get_capture_lock(index):
                    self.last_frames[index] = (time.time(), frame_bytes)
                
                time.sleep(0.04)  # ~25 FPS
            except Exception as e:
                logger.error(f"Error in camera loop {index}: {e}")
                time.sleep(1.0)

    def capture(self, index):
        if not self.is_running:
            return None

        # Đảm bảo luồng background đã được khởi chạy cho camera này
        if index not in self.threads or not self.threads[index].is_alive():
            self.start_camera_thread(index)

        now = time.time()
        # Đợi tối đa 2 giây nếu chưa có frame nào từ luồng background
        timeout = 2.0
        start_wait = time.time()
        while index not in self.last_frames and (time.time() - start_wait < timeout):
            time.sleep(0.01)

        if index in self.last_frames:
            ts, frame_bytes = self.last_frames[index]
            # Nếu frame quá cũ (ví dụ camera bị treo quá 3 giây), trả về None
            if now - ts > 3.0:
                return None
            return frame_bytes
        return None

    def release_all(self):
        self.is_running = False
        # Chờ các thread dừng
        for index, thread in list(self.threads.items()):
            if thread.is_alive():
                thread.join(timeout=1.0)
        self.threads = {}
        
        # Giải phóng các camera
        for index, cap in list(self.cameras.items()):
            try:
                cap.release()
            except Exception:
                pass
        self.cameras = {}
        self.last_frames = {}
        logger.info("Released all cameras and stopped background threads.")


camera_manager = CameraManager()


def capture_image(camera_index: int):
    return camera_manager.capture(camera_index)
