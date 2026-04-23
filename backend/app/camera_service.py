import cv2
import time
import logging

logger = logging.getLogger(__name__)

# ID của Camera (Mặc định là 1 và 2 cho 2 webcam USB)
# Nếu không chạy, hãy dùng camera_test.py để tìm ID đúng
CAMERA_IN_INDEX = 1 
CAMERA_OUT_INDEX = 2

def capture_image(camera_index: int):
    """
    Mở camera, lấy 1 khung hình và trả về dưới dạng bytes.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.error(f"Khong the mo Camera Index {camera_index}")
        return None
    
    # Đợi một chút để camera ổn định ánh sáng và lấy nét
    time.sleep(0.6) 
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        logger.error(f"Khong the doc frame tu Camera Index {camera_index}")
        return None
    
    # Encode sang định dạng JPG để gửi cho AI service
    _, buffer = cv2.imencode('.jpg', frame)
    return buffer.tobytes()
