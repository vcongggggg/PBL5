"""
Module nhận diện biển số bằng YOLO + OCR (EasyOCR).

- YOLO dùng để phát hiện vùng biển số trên ảnh.
- EasyOCR dùng để đọc text từ vùng biển số.

Nếu không tải được model hoặc xảy ra lỗi khi xử lý ảnh,
hàm sẽ trả về giá trị giả lập để hệ thống không bị dừng.
"""

from typing import Tuple
import re

import cv2
import numpy as np
from ultralytics import YOLO
import easyocr

_yolo_model = None
_ocr_reader = None


def normalize_plate(text: str) -> str:
    """Normalize bien so: upper, bo khoang trang, loai ky tu khong hop le."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", "", text).upper()
    cleaned = re.sub(r"[^A-Z0-9\.\-]", "", cleaned)
    return cleaned


def is_valid_vn_plate(text: str) -> bool:
    """Kiem tra dinh dang bien so Viet Nam theo cac mau pho bien."""
    if not text:
        return False
    patterns = [
        r"^\d{2}[A-Z]-\d{3}\.\d{2}$",
        r"^\d{2}[A-Z]-\d{4,5}$",
        r"^\d{2}[A-Z]\d-\d{3}\.\d{2}$",
    ]
    return any(re.match(p, text) for p in patterns)


def _load_models() -> None:
    """Khởi tạo model YOLO và OCR (chỉ 1 lần)."""
    global _yolo_model, _ocr_reader

    if _yolo_model is None:
        try:
            # TODO: thay 'yolov8n.pt' bằng model biển số của bạn (vd: 'weights/plate_yolov8.pt')
            _yolo_model = YOLO("yolov8n.pt")
        except Exception:
            _yolo_model = None

    if _ocr_reader is None:
        try:
            _ocr_reader = easyocr.Reader(["en"], gpu=False)
        except Exception:
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
        return "51F-123.45", 0.5

    # bytes → ảnh OpenCV (BGR)
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return "UNKNOWN", 0.0

    try:
        results = _yolo_model(img)[0]
    except Exception:
        return "UNKNOWN", 0.0

    if not results.boxes:
        return "UNKNOWN", 0.0

    best_box = max(results.boxes, key=lambda b: float(b.conf[0]))
    x1, y1, x2, y2 = map(int, best_box.xyxy[0])
    conf_det = float(best_box.conf[0])

    plate_roi = img[y1:y2, x1:x2]
    if plate_roi.size == 0:
        return "UNKNOWN", 0.0

    try:
        ocr_results = _ocr_reader.readtext(plate_roi)
    except Exception:
        return "UNKNOWN", 0.0

    if not ocr_results:
        return "UNKNOWN", 0.0

    best_text, best_ocr_conf = "", 0.0
    for _, text, conf in ocr_results:
        if conf > best_ocr_conf:
            best_text = text
            best_ocr_conf = float(conf)

    if not best_text:
        return "UNKNOWN", 0.0

    plate = normalize_plate(best_text)
    confidence = min(conf_det, best_ocr_conf)

    return plate, confidence


def recognize_plate_demo() -> Tuple[str, float]:
    """Hàm demo khi ESP32 chỉ gửi sự kiện, tạm trả biển số mẫu."""
    return "51F-123.45", 0.9

