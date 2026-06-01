"""
Module nhận diện biển số bằng YOLO + OCR (PaddleOCR).

- YOLO dùng để phát hiện vùng biển số trên ảnh.
- PaddleOCR dùng để đọc text từ vùng biển số.

Nếu không tải được model hoặc xảy ra lỗi khi xử lý ảnh,
hàm sẽ trả về giá trị giả lập để hệ thống không bị dừng.
"""

import os
import logging
import re
from typing import Tuple

import cv2
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR

# Bỏ qua kiểm tra kết nối tới model hoster khi khởi tạo PaddleOCR (v5/PaddleX API).
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

_yolo_model = None
_ocr_reader = None
logger = logging.getLogger(__name__)


def normalize_plate(text: str) -> str:
    """Normalize bien so: upper, bo khoang trang, loai ky tu khong hop le."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", "", text).upper()
    cleaned = re.sub(r"[^A-Z0-9\.\-]", "", cleaned)
    return cleaned


def is_valid_vn_plate(text: str) -> bool:
    """Validate bien so theo kieu tong quat, khong gioi han mau Viet Nam."""
    normalized = normalize_plate(text)
    if not normalized:
        return False

    # Loai bo ky tu phan cach de kiem tra do dai/ky tu cot loi.
    compact = re.sub(r"[\.\-]", "", normalized)
    if len(compact) < 4 or len(compact) > 12:
        return False

    has_digit = any(ch.isdigit() for ch in compact)
    has_letter = any(ch.isalpha() for ch in compact)

    # Bien so quoc te thuong co ca chu va so; van chap nhan truong hop OCR mat chu.
    if has_digit and has_letter:
        return True
    return has_digit and len(compact) >= 5


def _load_models() -> None:
    """Khởi tạo model YOLO và PaddleOCR (chỉ 1 lần)."""
    global _yolo_model, _ocr_reader

    if _yolo_model is None:
        try:
            env_model_path = os.getenv("PLATE_MODEL_PATH", "").strip()
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            default_model_path = os.path.join(base_dir, "best.pt")
            model_path = env_model_path or default_model_path
            _yolo_model = YOLO(model_path)
            logger.info("Loaded YOLO plate model from %s", model_path)
        except Exception:
            logger.exception("Failed to load YOLO model from configured path")
            try:
                _yolo_model = YOLO("yolov8n.pt")
                logger.warning("Falling back to yolov8n.pt because the configured plate model could not be loaded")
            except Exception:
                logger.exception("Failed to load fallback YOLO model yolov8n.pt")
                _yolo_model = None

    if _ocr_reader is None:
        try:
            logging.getLogger('ppocr').setLevel(logging.ERROR)
            _ocr_reader = PaddleOCR(use_textline_orientation=True, lang='en')
            logger.info("Initialized PaddleOCR successfully")
        except Exception:
            logger.exception("Failed to initialize PaddleOCR")
            _ocr_reader = None


def recognize_plate_from_bytes(image_bytes: bytes) -> Tuple[str, float]:
    """
    Nhận vào dữ liệu ảnh (bytes) và trả về:
    - plate: biển số ở dạng chuỗi
    - confidence: độ tin cậy (0–1)
    """
    _load_models()

    # Nếu model không tải được → trả về giả lập
    if _yolo_model is None or _ocr_reader is None:
        logger.warning(
            "Plate recognition is using fallback output because model init failed. yolo_ready=%s, ocr_ready=%s",
            _yolo_model is not None,
            _ocr_reader is not None,
        )
        return "51F-123.45", 0.5

    # bytes → ảnh OpenCV (BGR)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        logger.warning("Failed to decode uploaded image bytes into an OpenCV image")
        return "UNKNOWN", 0.0

    try:
        results = _yolo_model(img)[0]
    except Exception:
        logger.exception("YOLO inference failed while detecting plate region")
        return "UNKNOWN", 0.0

    if not results.boxes:
        logger.info("YOLO did not detect any plate region in the uploaded image")
        return "UNKNOWN", 0.0

    best_box = max(results.boxes, key=lambda b: float(b.conf[0]))
    x1, y1, x2, y2 = map(int, best_box.xyxy[0])
    conf_det = float(best_box.conf[0])

    plate_roi = img[y1:y2, x1:x2]
    if plate_roi.size == 0:
        logger.warning("Detected plate ROI is empty after cropping: (%s, %s, %s, %s)", x1, y1, x2, y2)
        return "UNKNOWN", 0.0

    try:
        ocr_results = _ocr_reader.predict(plate_roi)
    except Exception:
        logger.exception("PaddleOCR failed while reading cropped plate ROI")
        return "UNKNOWN", 0.0

    if not ocr_results:
        logger.info("PaddleOCR returned no text for the detected plate ROI")
        return "UNKNOWN", 0.0

    all_texts = []
    best_ocr_conf = 0.0

    for res in ocr_results:
        texts = res.get('rec_texts', [])
        scores = res.get('rec_scores', [])
        for i, text in enumerate(texts):
            score = scores[i] if i < len(scores) else 0.0
            if text:
                all_texts.append(text)
                if float(score) > best_ocr_conf:
                    best_ocr_conf = float(score)

    combined_text = "".join(all_texts)
    
    if not combined_text:
        logger.info("PaddleOCR result contained no usable text candidates")
        return "UNKNOWN", 0.0

    plate = normalize_plate(combined_text)
    confidence = min(conf_det, best_ocr_conf)
    logger.info("Recognized plate=%s det_conf=%.3f ocr_conf=%.3f raw=%s", plate or "UNKNOWN", conf_det, best_ocr_conf, combined_text)

    return plate, confidence


def recognize_plate_demo() -> Tuple[str, float]:
    """Hàm demo khi ESP32 chỉ gửi sự kiện, tạm trả biển số mẫu."""
    return "51F-123.45", 0.9


