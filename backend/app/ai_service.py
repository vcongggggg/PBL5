"""
License plate recognition with YOLO + OCR.

- YOLO detects the plate region.
- PaddleOCR reads text from the detected plate crop.

If models cannot be loaded or image processing fails, the service returns
a fallback value so the rest of the system can keep running.
"""

import os
import logging
import re
import sys
from argparse import Namespace
from typing import Dict, List, Tuple

# Reduce verbose PaddlePaddle and PaddleX logs before importing them.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("GLOG_v", "0")
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("FLAGS_minloglevel", "2")
os.environ.setdefault("PADDLEX_DISABLE_RICH", "1")

# Silence noisy third-party library loggers.
for lib in ["paddle", "paddleocr", "paddlex", "ppocr", "ultralytics"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

import cv2
import numpy as np
from ultralytics import YOLO
from paddleocr import PaddleOCR

_yolo_model = None
_ocr_reader = None
logger = logging.getLogger(__name__)


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _default_custom_rec_model_dir() -> str:
    return os.path.join(_repo_root(), "backend", "models", "paddleocr_vn_plate_rec")


def _default_custom_rec_dict_path() -> str:
    return os.path.join(_default_custom_rec_model_dir(), "vn_plate_dict.txt")


def _default_paddleocr_repo() -> str:
    return os.path.join(_repo_root(), "TrainPaddle", "PaddleOCR")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y", "on"}


def _line_position(points) -> Tuple[float, float]:
    if points is None:
        return 0.0, 0.0
    arr = np.asarray(points, dtype=float)
    if arr.size == 0:
        return 0.0, 0.0
    if arr.ndim == 1 and arr.size >= 4:
        x1, y1, x2, y2 = arr[:4]
        return float(min(y1, y2)), float(min(x1, x2))
    arr = arr.reshape(-1, 2)
    return float(arr[:, 1].mean()), float(arr[:, 0].mean())


def _looks_like_plate_prefix(text: str) -> bool:
    normalized = normalize_plate(text)
    return bool(re.search(r"[A-Z]", normalized)) and any(ch.isdigit() for ch in normalized)


def _order_ocr_lines(items: List[Dict]) -> List[str]:
    with_boxes = [item for item in items if item.get("points") is not None]
    if with_boxes:
        return [
            item["text"]
            for item in sorted(
                items,
                key=lambda item: (*_line_position(item.get("points")), item.get("index", 0)),
            )
        ]

    texts = [item["text"] for item in items]
    if len(texts) == 2:
        first, second = texts
        if _looks_like_plate_prefix(second) and not _looks_like_plate_prefix(first):
            return [second, first]
    return texts


def _crop_by_points(img, points, pad_ratio: float = 0.08):
    h, w = img.shape[:2]
    if points is None:
        return img.copy()

    arr = np.asarray(points, dtype=float)
    if arr.size == 0:
        return img.copy()
    if arr.ndim == 1 and arr.size >= 4:
        x1, y1, x2, y2 = arr[:4]
        xs = [x1, x2]
        ys = [y1, y2]
    else:
        arr = arr.reshape(-1, 2)
        xs = arr[:, 0]
        ys = arr[:, 1]

    x1, x2 = float(min(xs)), float(max(xs))
    y1, y2 = float(min(ys)), float(max(ys))
    pad_x = max(2, int((x2 - x1) * pad_ratio))
    pad_y = max(2, int((y2 - y1) * pad_ratio))
    x1 = max(0, int(x1) - pad_x)
    y1 = max(0, int(y1) - pad_y)
    x2 = min(w, int(x2) + pad_x)
    y2 = min(h, int(y2) + pad_y)
    if x2 <= x1 or y2 <= y1:
        return img.copy()
    return img[y1:y2, x1:x2].copy()


def _extract_paddleocr_items(ocr_results) -> List[Dict]:
    items = []
    for res in ocr_results or []:
        if isinstance(res, dict):
            texts = res.get("rec_texts", [])
            scores = res.get("rec_scores", [])
            polys = res.get("rec_polys") or res.get("rec_boxes") or res.get("dt_polys") or []
            for i, text in enumerate(texts):
                items.append({
                    "text": str(text),
                    "score": float(scores[i]) if i < len(scores) else 0.0,
                    "points": polys[i] if i < len(polys) else None,
                    "index": i,
                })
    return sorted(items, key=lambda item: (*_line_position(item.get("points")), item.get("index", 0)))


class CustomPlateOcrReader:
    """Adapter for a repo-exported PaddleOCR recognition model."""

    def __init__(
        self,
        rec_model_dir: str,
        rec_char_dict_path: str,
        paddleocr_repo: str,
        use_gpu: bool = False,
    ):
        if not os.path.isdir(rec_model_dir):
            raise FileNotFoundError(f"Custom OCR recognition model dir not found: {rec_model_dir}")
        if not os.path.isfile(rec_char_dict_path):
            raise FileNotFoundError(f"Custom OCR char dict not found: {rec_char_dict_path}")
        if not os.path.isfile(os.path.join(paddleocr_repo, "tools", "infer", "predict_rec.py")):
            raise FileNotFoundError(f"PaddleOCR repo not found or incomplete: {paddleocr_repo}")

        if paddleocr_repo not in sys.path:
            sys.path.insert(0, paddleocr_repo)

        from tools.infer.predict_rec import TextRecognizer

        args = Namespace(
            rec_model_dir=rec_model_dir,
            rec_char_dict_path=rec_char_dict_path,
            rec_image_shape=os.getenv("PADDLE_OCR_REC_IMAGE_SHAPE", "3,48,160"),
            rec_algorithm=os.getenv("PADDLE_OCR_REC_ALGORITHM", "CRNN"),
            rec_batch_num=int(os.getenv("PADDLE_OCR_REC_BATCH_NUM", "6")),
            max_text_length=int(os.getenv("PADDLE_OCR_MAX_TEXT_LENGTH", "12")),
            use_space_char=False,
            use_gpu=use_gpu,
            use_xpu=False,
            use_npu=False,
            use_mlu=False,
            use_metax_gpu=False,
            use_gcu=False,
            ir_optim=True,
            use_tensorrt=False,
            min_subgraph_size=15,
            precision="fp32",
            gpu_mem=int(os.getenv("PADDLE_OCR_GPU_MEM", "500")),
            gpu_id=int(os.getenv("PADDLE_OCR_GPU_ID", "0")),
            enable_mkldnn=None,
            cpu_threads=int(os.getenv("PADDLE_OCR_CPU_THREADS", "10")),
            benchmark=False,
            save_log_path="./log_output/",
            show_log=False,
            use_onnx=False,
            onnx_providers=False,
            onnx_sess_options=False,
            return_word_box=False,
            rec_image_inverse=True,
            drop_score=0.0,
        )

        self._detector = PaddleOCR(use_textline_orientation=True, lang="en")
        self._recognizer = TextRecognizer(args)
        logger.info("Initialized custom PaddleOCR recognizer from %s", rec_model_dir)

    def predict(self, image):
        try:
            detector_results = self._detector.predict(image)
            detected_items = _extract_paddleocr_items(detector_results)
        except Exception:
            logger.exception("PaddleOCR detector failed before custom recognition; using whole ROI")
            detected_items = []

        crops = []
        points = []
        fallback_texts = []
        fallback_scores = []
        if detected_items:
            for item in detected_items:
                crop = _crop_by_points(image, item.get("points"))
                if crop is not None and crop.size:
                    crops.append(crop)
                    points.append(item.get("points"))
                    fallback_texts.append(item.get("text", ""))
                    fallback_scores.append(float(item.get("score", 0.0)))

        if not crops:
            crops = [image]
            points = [None]
            fallback_texts = [""]
            fallback_scores = [0.0]

        rec_results, _ = self._recognizer(crops)
        texts = []
        scores = []
        for idx, (rec_text, rec_score) in enumerate(rec_results):
            text = str(rec_text)
            score = float(rec_score)
            if not normalize_plate(text) and idx < len(fallback_texts):
                text = fallback_texts[idx]
                score = fallback_scores[idx]
            texts.append(text)
            scores.append(score)

        return [{
            "rec_texts": texts,
            "rec_scores": scores,
            "rec_polys": points,
        }]


def _decode_image(image_bytes: bytes):
    np_arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


def normalize_plate(text: str) -> str:
    """Normalize bien so: upper, bo khoang trang, loai ky tu khong hop le (bo ca dau cham va gach ngang)."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", "", text).upper()
    cleaned = re.sub(r"[^A-Z0-9]", "", cleaned)
    return cleaned


def is_valid_vn_plate(text: str) -> bool:
    """Validate bien so theo kieu tong quat, khong gioi han mau Viet Nam."""
    normalized = normalize_plate(text)
    if not normalized:
        return False

    # Loai bo ky tu phan cach de kiem tra do dai/ky tu cot loi.
    compact = re.sub(r"[\.\-]", "", normalized)
    if len(compact) < 7 or len(compact) > 12:
        return False

    has_digit = any(ch.isdigit() for ch in compact)
    has_letter = any(ch.isalpha() for ch in compact)

    # Bien so quoc te thuong co ca chu va so; van chap nhan truong hop OCR mat chu.
    if has_digit and has_letter:
        return True
    return has_digit and len(compact) >= 5


def _read_plate_roi(plate_roi) -> Tuple[str, float]:
    if _ocr_reader is None:
        return "", 0.0

    try:
        ocr_results = _ocr_reader.predict(plate_roi)
    except Exception:
        logger.exception("PaddleOCR failed while reading cropped plate ROI")
        return "", 0.0

    if not ocr_results:
        return "", 0.0

    text_items = []
    best_ocr_conf = 0.0

    for res in ocr_results:
        texts = res.get('rec_texts', [])
        scores = res.get('rec_scores', [])
        polys = res.get('rec_polys') or res.get('rec_boxes') or res.get('dt_polys') or []
        for i, text in enumerate(texts):
            score = scores[i] if i < len(scores) else 0.0
            if text:
                text_items.append({
                    "text": text,
                    "score": float(score),
                    "points": polys[i] if i < len(polys) else None,
                    "index": i,
                })
                if float(score) > best_ocr_conf:
                    best_ocr_conf = float(score)

    ordered_texts = _order_ocr_lines(text_items)
    return normalize_plate("".join(ordered_texts)), best_ocr_conf


def _load_yolo_model() -> None:
    global _yolo_model

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


def _load_ocr_reader() -> None:
    global _ocr_reader

    if _ocr_reader is None:
        try:
            logging.getLogger('ppocr').setLevel(logging.ERROR)
            rec_model_dir = os.getenv("PADDLE_OCR_REC_MODEL_DIR", "").strip()
            if not rec_model_dir:
                default_rec_model_dir = _default_custom_rec_model_dir()
                if os.path.isfile(os.path.join(default_rec_model_dir, "inference.yml")):
                    rec_model_dir = default_rec_model_dir

            if rec_model_dir:
                _ocr_reader = CustomPlateOcrReader(
                    rec_model_dir=rec_model_dir,
                    rec_char_dict_path=os.getenv("PADDLE_OCR_REC_CHAR_DICT_PATH", "").strip()
                    or _default_custom_rec_dict_path(),
                    paddleocr_repo=os.getenv("PADDLEOCR_REPO", "").strip() or _default_paddleocr_repo(),
                    use_gpu=_env_bool("PADDLE_OCR_USE_GPU", False),
                )
            else:
                _ocr_reader = PaddleOCR(use_textline_orientation=True, lang='en')
                logger.info("Initialized default PaddleOCR successfully")
        except Exception:
            logger.exception("Failed to initialize PaddleOCR")
            _ocr_reader = None


def _load_models() -> None:
    """Initialize YOLO and OCR models once."""
    _load_yolo_model()
    _load_ocr_reader()

def detect_plate_candidates_from_bytes(image_bytes: bytes) -> List[Dict]:
    """Return YOLO plate candidates with bbox/confidence, without running OCR."""
    _load_yolo_model()

    if _yolo_model is None:
        return []

    img = _decode_image(image_bytes)
    if img is None:
        return []

    try:
        results = _yolo_model(img)[0]
    except Exception:
        logger.exception("YOLO inference failed while detecting plate candidates")
        return []

    candidates = []
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        if x2 <= x1 or y2 <= y1:
            continue
        candidates.append({
            "bbox": [x1, y1, x2, y2],
            "det_confidence": float(box.conf[0]),
        })

    candidates.sort(key=lambda item: item["det_confidence"], reverse=True)
    return candidates


def recognize_plate_in_bbox(image_bytes: bytes, bbox: List[int]) -> Tuple[str, float]:
    """Run OCR on a known plate bbox."""
    _load_ocr_reader()

    if _ocr_reader is None:
        return "", 0.0

    img = _decode_image(image_bytes)
    if img is None:
        return "", 0.0

    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(0, min(w, int(x2)))
    y2 = max(0, min(h, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return "", 0.0

    plate_roi = img[y1:y2, x1:x2]
    if plate_roi.size == 0:
        return "", 0.0

    return _read_plate_roi(plate_roi)


def recognize_plate_from_bytes(image_bytes: bytes) -> Tuple[str, float]:
    """
    Accept image bytes and return:
    - plate: normalized license plate text
    - confidence: recognition confidence from 0 to 1
    """
    _load_models()

    # Return fallback output if either model cannot be loaded.
    if _yolo_model is None or _ocr_reader is None:
        logger.warning(
            "Plate recognition is using fallback output because model init failed. yolo_ready=%s, ocr_ready=%s",
            _yolo_model is not None,
            _ocr_reader is not None,
        )
        return "51F-123.45", 0.5

    # Decode bytes to an OpenCV BGR image.
    img = _decode_image(image_bytes)
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

    plate, best_ocr_conf = _read_plate_roi(plate_roi)
    if not plate:
        logger.info("PaddleOCR result contained no usable text candidates")
        return "UNKNOWN", 0.0

    confidence = min(conf_det, best_ocr_conf)
    logger.info("Recognized plate=%s det_conf=%.3f ocr_conf=%.3f", plate or "UNKNOWN", conf_det, best_ocr_conf)

    return plate, confidence


def recognize_plate_demo() -> Tuple[str, float]:
    """Demo fallback for sensor-only ESP32 events."""
    return "51F-123.45", 0.9

