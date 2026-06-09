import logging
import os
import uuid
from typing import List, Optional

from ..core.time_utils import get_vietnam_now


logger = logging.getLogger("uvicorn")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEGACY_UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
BASE_DIR = BACKEND_DIR
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def migrate_legacy_uploads() -> int:
    """Copy images saved by the split-branch path bug into the served upload dir."""
    if not os.path.isdir(LEGACY_UPLOAD_DIR) or os.path.abspath(LEGACY_UPLOAD_DIR) == os.path.abspath(UPLOAD_DIR):
        return 0

    migrated = 0
    for filename in os.listdir(LEGACY_UPLOAD_DIR):
        src = os.path.join(LEGACY_UPLOAD_DIR, filename)
        dst = os.path.join(UPLOAD_DIR, filename)
        if not os.path.isfile(src) or os.path.exists(dst):
            continue
        try:
            import shutil

            shutil.copy2(src, dst)
            migrated += 1
        except Exception:
            logger.exception("Failed to migrate legacy upload %s", src)
    return migrated


def save_upload_image(image_bytes: bytes, original_name: Optional[str]) -> Optional[str]:
    if not image_bytes:
        return None

    ext = os.path.splitext(original_name or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
        ext = ".jpg"

    filename = f"capture_{get_vietnam_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    with open(file_path, "wb") as file_obj:
        file_obj.write(image_bytes)

    return file_path


def image_url_from_path(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None
    try:
        filename = os.path.basename(image_path)
    except TypeError:
        return None
    if not filename:
        return None
    return f"/uploads/{filename}"


def crop_image_bytes_by_bbox(
    image_bytes: Optional[bytes],
    bbox: Optional[List[int]],
    padding_ratio: float = 0.04,
) -> Optional[bytes]:
    if not image_bytes or not bbox:
        return None
    try:
        import cv2
        import numpy as np

        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None

        height, width = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        bw = max(1, x2 - x1)
        bh = max(1, y2 - y1)
        pad_x = int(bw * padding_ratio)
        pad_y = int(bh * padding_ratio)

        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(width, x2 + pad_x)
        y2 = min(height, y2 + pad_y)

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        ok, buffer = cv2.imencode(".jpg", crop)
        return buffer.tobytes() if ok else None
    except Exception:
        logger.exception("Failed to crop plate evidence image")
        return None
