from collections import deque
from datetime import datetime
from threading import Lock
from typing import Deque, Dict, List

from ..core.time_utils import get_vietnam_now


MAX_FIRE_TELEMETRY_POINTS = 300

_telemetry_points: Deque[Dict] = deque(maxlen=MAX_FIRE_TELEMETRY_POINTS)
_telemetry_lock = Lock()


def add_fire_telemetry(
    device_id: str,
    digital_value: int,
    analog_value: int,
    fire_detected: bool,
    fire_alert_active: bool,
    timestamp: datetime | None = None,
) -> Dict:
    point = {
        "device_id": device_id,
        "digital_value": int(digital_value),
        "analog_value": int(analog_value),
        "fire_detected": bool(fire_detected),
        "fire_alert_active": bool(fire_alert_active),
        "timestamp": (timestamp or get_vietnam_now()).isoformat(),
    }
    with _telemetry_lock:
        _telemetry_points.append(point)
    return point


def list_fire_telemetry(limit: int = 120) -> List[Dict]:
    safe_limit = max(1, min(int(limit or 120), MAX_FIRE_TELEMETRY_POINTS))
    with _telemetry_lock:
        return list(_telemetry_points)[-safe_limit:]
