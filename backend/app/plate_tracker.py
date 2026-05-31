import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import ai_service


BBox = List[int]


def _iou(a: BBox, b: BBox) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _bbox_area(bbox: BBox) -> int:
    x1, y1, x2, y2 = bbox
    return max(0, x2 - x1) * max(0, y2 - y1)


@dataclass
class GateTrackState:
    active_until: float = 0.0
    bbox: Optional[BBox] = None
    det_confidence: float = 0.0
    stable_count: int = 0
    last_seen_at: float = 0.0
    best_plate: str = "UNKNOWN"
    best_confidence: float = 0.0
    best_bbox: Optional[BBox] = None
    best_image_bytes: Optional[bytes] = None
    attempts: int = 0
    status: str = "idle"
    lock: threading.Lock = field(default_factory=threading.Lock)


class PlateTrackerManager:
    def __init__(self):
        self.states: Dict[str, GateTrackState] = {
            "entry": GateTrackState(),
            "exit": GateTrackState(),
        }

    def start(self, gate_type: str, duration_seconds: float) -> None:
        state = self.states[gate_type]
        with state.lock:
            state.active_until = time.time() + duration_seconds
            state.bbox = None
            state.det_confidence = 0.0
            state.stable_count = 0
            state.last_seen_at = 0.0
            state.best_plate = "UNKNOWN"
            state.best_confidence = 0.0
            state.best_bbox = None
            state.best_image_bytes = None
            state.attempts = 0
            state.status = "tracking"

    def stop(self, gate_type: str, status: str = "idle") -> None:
        state = self.states[gate_type]
        with state.lock:
            state.active_until = 0.0
            state.status = status

    def snapshot(self, gate_type: str) -> Dict:
        state = self.states[gate_type]
        with state.lock:
            return {
                "active": time.time() <= state.active_until,
                "bbox": list(state.bbox) if state.bbox else None,
                "det_confidence": state.det_confidence,
                "stable_count": state.stable_count,
                "best_plate": state.best_plate,
                "best_confidence": state.best_confidence,
                "best_bbox": list(state.best_bbox) if state.best_bbox else None,
                "attempts": state.attempts,
                "status": state.status,
                "last_seen_at": state.last_seen_at,
            }

    def update(self, gate_type: str, image_bytes: bytes, threshold: float) -> Dict:
        state = self.states[gate_type]
        candidates = ai_service.detect_plate_candidates_from_bytes(image_bytes)

        with state.lock:
            state.attempts += 1
            now = time.time()
            if not candidates:
                state.status = "searching"
                return {
                    "active": time.time() <= state.active_until,
                    "bbox": list(state.bbox) if state.bbox else None,
                    "det_confidence": state.det_confidence,
                    "stable_count": state.stable_count,
                    "best_plate": state.best_plate,
                    "best_confidence": state.best_confidence,
                    "best_bbox": list(state.best_bbox) if state.best_bbox else None,
                    "best_image_bytes": state.best_image_bytes,
                    "attempts": state.attempts,
                    "status": state.status,
                    "last_seen_at": state.last_seen_at,
                    "accepted": False,
                }

            selected = self._select_candidate(state.bbox, candidates)
            bbox = selected["bbox"]
            det_confidence = float(selected["det_confidence"])
            same_track = bool(state.bbox and _iou(state.bbox, bbox) >= 0.25)
            state.stable_count = state.stable_count + 1 if same_track else 1
            state.bbox = bbox
            state.det_confidence = det_confidence
            state.last_seen_at = now
            state.status = "tracking"

        plate, ocr_confidence = ai_service.recognize_plate_in_bbox(image_bytes, bbox)
        combined_confidence = min(det_confidence, ocr_confidence) if plate else 0.0
        valid_plate = ai_service.is_valid_vn_plate(plate)

        with state.lock:
            if combined_confidence > state.best_confidence or (valid_plate and state.best_plate == "UNKNOWN"):
                state.best_plate = plate or "UNKNOWN"
                state.best_confidence = combined_confidence
                state.best_bbox = list(bbox)
                state.best_image_bytes = image_bytes

            if valid_plate and combined_confidence >= threshold and state.stable_count >= 2:
                state.status = "accepted"
            elif plate:
                state.status = "reading"

            return {
                "active": time.time() <= state.active_until,
                "bbox": list(state.bbox) if state.bbox else None,
                "det_confidence": state.det_confidence,
                "stable_count": state.stable_count,
                "best_plate": state.best_plate,
                "best_confidence": state.best_confidence,
                "best_bbox": list(state.best_bbox) if state.best_bbox else None,
                "best_image_bytes": state.best_image_bytes,
                "attempts": state.attempts,
                "status": state.status,
                "last_seen_at": state.last_seen_at,
                "accepted": state.status == "accepted",
            }

    def annotate_frame(self, gate_type: str, image_bytes: bytes) -> bytes:
        state_data = self.snapshot(gate_type)
        last_seen_at = float(state_data.get("last_seen_at") or 0.0)
        if not state_data.get("active") and time.time() - last_seen_at > 5.0:
            return image_bytes

        bbox = state_data.get("bbox") or state_data.get("best_bbox")
        if not bbox:
            return image_bytes

        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return image_bytes

        x1, y1, x2, y2 = [int(v) for v in bbox]
        color = (40, 220, 120) if state_data.get("status") == "accepted" else (0, 190, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"{state_data.get('best_plate') or 'TRACKING'} {state_data.get('best_confidence', 0.0):.2f}"
        if state_data.get("status"):
            label = f"{state_data['status'].upper()} | {label}"

        label_y = max(20, y1 - 8)
        cv2.putText(frame, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        _, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes()

    @staticmethod
    def _select_candidate(current_bbox: Optional[BBox], candidates: List[Dict]) -> Dict:
        if not current_bbox:
            return max(candidates, key=lambda item: (item["det_confidence"], _bbox_area(item["bbox"])))

        return max(
            candidates,
            key=lambda item: (
                _iou(current_bbox, item["bbox"]),
                item["det_confidence"],
                _bbox_area(item["bbox"]),
            ),
        )


plate_tracker = PlateTrackerManager()
