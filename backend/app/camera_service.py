import os
# Tắt log lỗi từ core C++ của OpenCV (Phải đặt trước khi import cv2)
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["PYTHONWARNINGS"] = "ignore"

import cv2
import threading
import logging
import time
import subprocess

logger = logging.getLogger(__name__)

# ============ CẤU HÌNH CAMERA ============
# Tên camera laptop để hệ thống tự động BỎ QUA nó.
# Chạy "python check_cam_names.py" để xem tên chính xác.
LAPTOP_CAM_NAME = "USB2.0 HD UVC WebCam"

# Chỉ số dự phòng nếu auto-detect thất bại
CAMERA_IN_INDEX = 0
CAMERA_OUT_INDEX = 2

# Cho phép ghi đè index camera qua biến môi trường để cấu hình linh hoạt
env_in = os.getenv("CAMERA_IN_INDEX")
env_out = os.getenv("CAMERA_OUT_INDEX")
USE_AUTO_DETECT = True

if env_in is not None and env_out is not None:
    try:
        CAMERA_IN_INDEX = int(env_in)
        CAMERA_OUT_INDEX = int(env_out)
        USE_AUTO_DETECT = False
    except ValueError:
        pass


def auto_detect_camera_indices():
    """
    Tự động tìm 2 webcam rời bằng cách loại trừ camera laptop.
    Logic: Quét tất cả index, tìm index nào là laptop, bỏ qua nó,
    gán 2 cái còn lại cho Làn Vào và Làn Ra.
    """
    global CAMERA_IN_INDEX, CAMERA_OUT_INDEX

    if not USE_AUTO_DETECT:
        return

    try:
        # Bước 1: Tìm tất cả index camera đang hoạt động
        working_indices = []
        for i in range(6):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    working_indices.append(i)
                cap.release()

        logger.info(f"Auto-detect: Camera indices hoạt động: {working_indices}")

        if len(working_indices) < 2:
            logger.warning("Auto-detect: Không đủ 2 camera. Dùng chỉ số mặc định.")
            return

        if len(working_indices) == 2:
            # Chỉ có 2 camera → gán trực tiếp, không cần loại trừ
            CAMERA_IN_INDEX = working_indices[0]
            CAMERA_OUT_INDEX = working_indices[1]
            logger.info(f"Auto-detect: Chỉ có 2 camera → Làn VÀO={CAMERA_IN_INDEX}, Làn RA={CAMERA_OUT_INDEX}")
            return

        # Bước 2: Có >= 3 camera → cần tìm và loại trừ camera laptop
        # Tắt camera laptop tạm thời qua PowerShell để xác định index của nó
        laptop_index = _find_laptop_index(working_indices)

        if laptop_index is not None:
            logger.info(f"Auto-detect: Camera laptop ở index {laptop_index} → bỏ qua")
            external_cams = [i for i in working_indices if i != laptop_index]
        else:
            logger.warning("Auto-detect: Không xác định được camera laptop. Dùng chỉ số mặc định.")
            return

        if len(external_cams) >= 2:
            CAMERA_IN_INDEX = external_cams[0]
            CAMERA_OUT_INDEX = external_cams[1]
            logger.info(f"Auto-detect: KẾT QUẢ → Làn VÀO={CAMERA_IN_INDEX}, Làn RA={CAMERA_OUT_INDEX}")
        else:
            logger.warning("Auto-detect: Không đủ webcam rời. Dùng chỉ số mặc định.")

    except Exception as e:
        logger.error(f"Auto-detect thất bại: {e}. Dùng mặc định IN={CAMERA_IN_INDEX}, OUT={CAMERA_OUT_INDEX}")


def _find_laptop_index(working_indices):
    """
    Xác định index của camera laptop bằng cách tạm tắt nó qua PowerShell
    rồi kiểm tra index nào biến mất.
    """
    try:
        # Thử tắt camera laptop
        disable_cmd = (
            f'Get-PnpDevice | Where-Object {{ $_.FriendlyName -like "*{LAPTOP_CAM_NAME}*" }} '
            f'| Disable-PnpDevice -Confirm:$false'
        )
        result = subprocess.run(
            ['powershell', '-Command', disable_cmd],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            # Không có quyền Admin → dùng phương pháp dự phòng
            logger.info("Auto-detect: Không có quyền tắt camera laptop. Dùng phương pháp dự phòng.")
            return _find_laptop_index_fallback(working_indices)

        # Đợi Windows xử lý
        time.sleep(1)

        # Quét lại xem index nào biến mất
        still_working = []
        for i in working_indices:
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    still_working.append(i)
                cap.release()

        # Bật lại camera laptop ngay lập tức
        enable_cmd = (
            f'Get-PnpDevice | Where-Object {{ $_.FriendlyName -like "*{LAPTOP_CAM_NAME}*" }} '
            f'| Enable-PnpDevice -Confirm:$false'
        )
        subprocess.run(
            ['powershell', '-Command', enable_cmd],
            capture_output=True, text=True, timeout=10
        )
        time.sleep(1)

        # Index bị mất chính là camera laptop
        disappeared = set(working_indices) - set(still_working)
        if len(disappeared) == 1:
            return disappeared.pop()

        return None

    except Exception as e:
        logger.error(f"Lỗi khi tìm laptop camera: {e}")
        return _find_laptop_index_fallback(working_indices)


def _find_laptop_index_fallback(working_indices):
    """
    Phương pháp dự phòng: Giả định camera laptop KHÔNG nằm ở index đầu hoặc cuối.
    Trên hầu hết máy Windows, laptop cam thường ở giữa danh sách (index 1).
    """
    if len(working_indices) == 3:
        # Thử index giữa (thường là laptop)
        middle = working_indices[1]
        logger.info(f"Auto-detect (fallback): Giả định laptop ở index {middle}")
        return middle
    return None


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

    def capture(self, index):
        now = time.time()
        if index in self.last_frames:
            ts, frame_bytes = self.last_frames[index]
            if now - ts < 0.03:
                return frame_bytes

        lock = self._get_capture_lock(index)
        with lock:
            if index in self.last_frames:
                ts, frame_bytes = self.last_frames[index]
                if now - ts < 0.03:
                    return frame_bytes

            cap = self.get_camera(index)
            if cap is None:
                return None

            cap.grab()

            ret, frame = cap.read()
            if not ret:
                logger.error(f"Failed to read frame from Camera {index}")
                return None

            _, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
            self.last_frames[index] = (time.time(), frame_bytes)
            return frame_bytes

    def release_all(self):
        for index, cap in self.cameras.items():
            cap.release()
        self.cameras = {}
        self.last_frames = {}


camera_manager = CameraManager()


def capture_image(camera_index: int):
    return camera_manager.capture(camera_index)
