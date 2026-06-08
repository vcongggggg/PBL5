from datetime import datetime, time as dt_time, timezone, timedelta
import os
import time as time_module
import threading
import uuid
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger("uvicorn")

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status, WebSocket, WebSocketDisconnect, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
import json

from fastapi.responses import StreamingResponse
from . import ai_service, models, schemas, camera_service
from .camera_service import camera_manager
from .database import Base, engine, get_db, SessionLocal
from .mqtt_manager import mqtt_manager
from .plate_tracker import plate_tracker

Base.metadata.create_all(bind=engine)


ICT = timezone(timedelta(hours=7))

def get_vietnam_now() -> datetime:
    """Trả về datetime hiện tại theo múi giờ Việt Nam (ICT, UTC+7), dạng naive."""
    return datetime.now(ICT).replace(tzinfo=None)

def get_vietnam_date():
    return datetime.now(ICT).date()



# Keep old databases usable by adding new columns when needed.
def sync_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "parking_sessions" in table_names:
            parking_columns = {col["name"] for col in inspector.get_columns("parking_sessions")}
            required_parking_columns = {
                "gate_type": "VARCHAR(10) DEFAULT 'entry'",
                "trigger_type": "VARCHAR(10) DEFAULT 'sensor'",
                "trigger_source_id": "VARCHAR(50) NULL",
                "rfid_tag": "VARCHAR(100) NULL",
                "plate_in": "VARCHAR(20) NULL",
                "plate_out": "VARCHAR(20) NULL",
                "match_status": "VARCHAR(20) DEFAULT 'pending'",
                "confidence_in": "FLOAT NULL",
                "confidence_out": "FLOAT NULL",
                "rfid_card_id": "INT NULL",
                "rfid_card_type": "VARCHAR(20) NULL",
            }
            for col_name, ddl in required_parking_columns.items():
                if col_name in parking_columns:
                    continue
                conn.execute(text(f"ALTER TABLE parking_sessions ADD COLUMN {col_name} {ddl}"))

        if "subscriptions" in table_names:
            sub_columns = {col["name"] for col in inspector.get_columns("subscriptions")}
            required_sub_columns = {
                "monthly_user_id": "INT NULL",
                "registered_at": "DATETIME NULL",
            }
            for col_name, ddl in required_sub_columns.items():
                if col_name in sub_columns:
                    continue
                conn.execute(text(f"ALTER TABLE subscriptions ADD COLUMN {col_name} {ddl}"))

        if "rfid_cards" in table_names:
            rfid_columns = {col["name"] for col in inspector.get_columns("rfid_cards")}
            required_rfid_columns = {
                "status": "VARCHAR(20) DEFAULT 'available'",
            }
            for col_name, ddl in required_rfid_columns.items():
                if col_name in rfid_columns:
                    continue
                conn.execute(text(f"ALTER TABLE rfid_cards ADD COLUMN {col_name} {ddl}"))

        if "pending_scans" in table_names:
            pending_cols = {col["name"] for col in inspector.get_columns("pending_scans")}
            required_pending_cols = {
                "scan_token": "VARCHAR(100) NULL",
            }
            for col_name, ddl in required_pending_cols.items():
                if col_name in pending_cols:
                    continue
                conn.execute(text(f"ALTER TABLE pending_scans ADD COLUMN {col_name} {ddl}"))


sync_schema()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PBL5 Smart Parking API")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ============ WEBSOCKET MANAGER ============
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass

    async def broadcast(self, message: dict):
        from fastapi.encoders import jsonable_encoder
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(jsonable_encoder(message)))
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def notify_clients(event_type: str, data: dict):
    from fastapi.encoders import jsonable_encoder
    await manager.broadcast({"event": event_type, "data": jsonable_encoder(data)})

# API Key security verification
from fastapi.security.api_key import APIKeyHeader
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
    db: Session = Depends(get_db)
):
    expected_key = get_config_text(db, "api_secret_key", "pbl5_secure_key_12345")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing API Key"
        )
    return api_key

# IP của ESP32 để điều khiển mở barrier từ xa
esp32_ip = None

import asyncio
gate_locks = {
    "entry": asyncio.Lock(),
    "exit": asyncio.Lock()
}


def levenshtein_distance(s1: str, s2: str) -> int:
    """Tính khoảng cách Levenshtein giữa 2 chuỗi (cho phép so sánh biển số mờ)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def cleanup_expired_pending_scans_once(db: Session, max_age_seconds: int = 120) -> int:
    cutoff = get_vietnam_now() - timedelta(seconds=max_age_seconds)
    deleted = db.query(models.PendingScan).filter(models.PendingScan.created_at < cutoff).delete()
    if deleted:
        db.commit()
    return deleted


async def cleanup_expired_pending_scans_loop():
    """
    Background task chạy tuần kỳ mỗi 60 giây để dọn dẹp các PendingScan bị treo quá 2 phút.
    Điều này giải phóng hàng đợi khi xe kích hoạt cảm biến nhưng không quẹt thẻ rồi bỏ đi.
    """
    while True:
        try:
            await asyncio.sleep(60)
            db = SessionLocal()
            try:
                deleted = cleanup_expired_pending_scans_once(db)
                if deleted > 0:
                    logger.info(f"[CLEANUP] Đã tự động dọn dẹp {deleted} pending scans hết hạn.")
            except Exception as e:
                logger.error(f"[CLEANUP] Lỗi khi dọn dẹp pending scans: {e}")
                db.rollback()
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[CLEANUP] Lỗi ngoài dự kiến: {e}")

@app.on_event("startup")
async def startup_event():
    # Khởi chạy client MQTT
    loop = asyncio.get_event_loop()
    db = SessionLocal()
    try:
        mqtt_host = get_config_text(db, "mqtt_broker_host", "broker.hivemq.com")
        mqtt_port = int(get_config_text(db, "mqtt_broker_port", "1883"))
    except Exception:
        mqtt_host = "broker.hivemq.com"
        mqtt_port = 1883
    finally:
        db.close()
        
    mqtt_manager.init_app(loop, broker_host=mqtt_host, broker_port=mqtt_port)
    mqtt_manager.start()

    # Kích hoạt task dọn dẹp chạy ngầm định kỳ
    asyncio.create_task(cleanup_expired_pending_scans_loop())

@app.on_event("shutdown")
def shutdown_event():
    mqtt_manager.stop()
    camera_manager.is_running = False
    camera_manager.release_all()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_system_config_value(db: Session, key: str, default: float) -> float:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except (TypeError, ValueError):
        return default


def get_config_bool(db: Session, key: str, default: bool = False) -> bool:
    value = get_config_text(db, key, "1" if default else "0").strip().lower()
    return value in ["1", "true", "yes", "on", "enabled"]


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


def crop_image_bytes_by_bbox(image_bytes: Optional[bytes], bbox: Optional[List[int]], padding_ratio: float = 0.18) -> Optional[bytes]:
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


def get_config_text(db: Session, key: str, default: str = "") -> str:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config or not config.value:
        return default
    return str(config.value)


def set_config_text(db: Session, key: str, value: str) -> None:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if config:
        config.value = value
    else:
        db.add(models.SystemConfig(key=key, value=value))


def create_manual_gate_log(
    db: Session,
    gate_type: str,
    action: str,
    reason: Optional[str] = None,
    operator: Optional[str] = None,
    source: str = "web",
) -> None:
    db.add(models.ManualGateLog(
        gate_type=gate_type,
        action=action,
        reason=reason,
        operator=operator,
        source=source,
    ))
    db.commit()


def build_capacity_status(total_in_bay: int, max_slots: int, near_full_threshold: float = 0.7, almost_full_threshold: float = 0.9) -> dict:
    safe_max_slots = max(1, int(max_slots or 1))
    available_slots = max(0, safe_max_slots - total_in_bay)
    occupancy_percent = min(100.0, max(0.0, (total_in_bay / safe_max_slots) * 100.0))

    if total_in_bay >= safe_max_slots:
        status = "full"
        message = f"Bai xe da day ({total_in_bay}/{safe_max_slots}). Tam dung nhan xe vao."
    elif occupancy_percent >= almost_full_threshold * 100.0:
        status = "almost_full"
        message = f"Bai xe sap day, chi con {available_slots} cho trong."
    elif occupancy_percent >= near_full_threshold * 100.0:
        status = "near_full"
        message = f"Bai xe gan day ({total_in_bay}/{safe_max_slots}), nen dieu tiet xe vao."
    else:
        status = "normal"
        message = f"Bai xe con {available_slots} cho trong."

    return {
        "max_slots": safe_max_slots,
        "available_slots": available_slots,
        "occupancy_percent": round(occupancy_percent, 1),
        "capacity_status": status,
        "capacity_message": message,
        "near_full_threshold": near_full_threshold,
        "almost_full_threshold": almost_full_threshold,
    }


def count_open_sessions_by_ticket_type(db: Session) -> Tuple[int, int]:
    open_sessions = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_(None),
            models.ParkingSession.match_status != "ignored",
        )
        .all()
    )
    guest_count = 0
    monthly_count = 0
    for session in open_sessions:
        ticket_type = resolve_session_ticket_type(db, session)
        if ticket_type == "monthly":
            monthly_count += 1
        else:
            guest_count += 1
    return guest_count, monthly_count


def resolve_vehicle_type(db: Session, plate_norm: str) -> Tuple[str, str]:
    if not plate_norm or not ai_service.is_valid_vn_plate(plate_norm):
        return "unknown", "Bien so khong hop le"

    vehicle = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == plate_norm)
        .first()
    )
    if not vehicle:
        return "guest", "Xe vãng lai, cho phép vào bãi"

    today = get_vietnam_date()
    active_sub = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.vehicle_id == vehicle.id,
            models.Subscription.is_active == True,  # noqa: E712
            models.Subscription.start_date <= today,
            models.Subscription.end_date >= today,
        )
        .first()
    )
    if active_sub:
        return "monthly", "Xe vé tháng còn hạn"
    return "guest", "Xe vé tháng hết hạn, xử lý như xe vãng lai"


def calculate_fee(now: datetime, session: models.ParkingSession, db: Session, ticket_type: str = "guest") -> Tuple[int, float]:
    duration_seconds = (now - session.time_in).total_seconds()
    duration_minutes = int(duration_seconds // 60)

    # Xe vé tháng còn hạn -> miễn phí
    if ticket_type == "monthly":
        return duration_minutes, 0.0

    price_per_hour = get_system_config_value(db, "price_per_hour", 5000.0)
    duration_hours = max(duration_seconds / 3600.0, 0.0)

    hours_rounded = int(duration_hours) if duration_hours.is_integer() else int(duration_hours) + 1
    if hours_rounded == 0:
        hours_rounded = 1

    fee = hours_rounded * price_per_hour
    return duration_minutes, fee


def resolve_session_ticket_type(db: Session, session: models.ParkingSession) -> str:
    if session.rfid_card_type in ["monthly", "guest"]:
        return session.rfid_card_type

    vehicle_id = session.vehicle_id
    if not vehicle_id and session.plate_number:
        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == session.plate_number)
            .first()
        )
        vehicle_id = vehicle.id if vehicle else None

    if not vehicle_id:
        return "guest"

    parked_date = session.time_in.date()
    has_monthly = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.vehicle_id == vehicle_id,
            models.Subscription.start_date <= parked_date,
            models.Subscription.end_date >= parked_date,
        )
        .first()
    )
    return "monthly" if has_monthly else "guest"


def get_rfid_card(db: Session, rfid_tag: Optional[str]) -> Optional[models.RFIDCard]:
    if not rfid_tag:
        return None
    tag_norm = rfid_tag.strip().upper().replace(" ", "").replace(":", "")
    return (
        db.query(models.RFIDCard)
        .filter(models.RFIDCard.card_uid == tag_norm)
        .first()
    )


def validate_rfid_for_scan(
    db: Session,
    trigger_type: str,
    rfid_tag: Optional[str],
    recognized_plate: str,
    gate_type: str,
) -> Tuple[Optional[models.RFIDCard], Optional[str]]:
    if trigger_type != "rfid":
        return None, None

    if not rfid_tag:
        return None, "RFID trigger can thiet lap rfid_tag"

    card = get_rfid_card(db, rfid_tag)
    if not card:
        return None, "Khong tim thay the RFID"
    if not card.is_active:
        if gate_type == "exit":
            return None, "Thẻ RFID đã bị khóa. Cần bảo vệ xác nhận thủ công để cho xe ra."
        return None, "The RFID da bi khoa"
    if card.expired_at and card.expired_at < get_vietnam_now():
        return None, "The RFID da het han"
    if card.card_type not in ["monthly", "guest"]:
        return None, "Loai the RFID khong hop le"
    if gate_type == "entry" and card.status == "in_use":
        return None, "Thẻ đang được sử dụng bởi xe khác"

    if card.card_type == "monthly":
        # Lấy thông tin xe đã được đăng ký với thẻ tháng này
        registered_vehicle = card.vehicle
        if not registered_vehicle:
            return None, "The thang chua duoc gan cho phuong tien nao"

        # Nếu biển số xe nhận diện hợp lệ và không phải UNKNOWN, ta đối chiếu biển số
        if recognized_plate and recognized_plate != "UNKNOWN":
            plate_distance = levenshtein_distance(
                ai_service.normalize_plate(registered_vehicle.plate_number),
                recognized_plate
            )
            # Cho phép sai lệch tối đa 1 ký tự do nhận diện biển số có thể sai lệch nhỏ
            if plate_distance > 1:
                return None, f"Bien so dang quet ({recognized_plate}) khong khop voi dang ky ve thang ({registered_vehicle.plate_number})"
        
        # Kiểm tra thời hạn đăng ký vé tháng của xe đó
        today = get_vietnam_date()
        active_sub = (
            db.query(models.Subscription)
            .filter(
                models.Subscription.vehicle_id == registered_vehicle.id,
                models.Subscription.is_active == True,  # noqa: E712
                models.Subscription.start_date <= today,
                models.Subscription.end_date >= today,
            )
            .order_by(models.Subscription.id.desc())
            .first()
        )
        if not active_sub:
            return None, "Dang ky ve thang da het han hoac khong hoat dong"
        if card.monthly_user_id and active_sub.monthly_user_id and card.monthly_user_id != active_sub.monthly_user_id:
            return None, "The RFID khong khop chu dang ky ve thang"

    return card, None


async def process_gate_scan(
    db: Session,
    image_bytes: Optional[bytes],
    filename: Optional[str],
    gate_type: str,
    trigger_type: str,
    source_id: Optional[str],
    rfid_tag: Optional[str],
    override_plate: Optional[str] = None,
    override_confidence: Optional[float] = None,
    existing_image_path: Optional[str] = None,
) -> schemas.GateScanResponse:
    gate_type = (gate_type or "entry").lower()
    trigger_type = (trigger_type or "sensor").lower()

    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    if trigger_type not in ["sensor", "rfid", "manual"]:
        raise HTTPException(status_code=400, detail="trigger_type must be sensor, rfid or manual")

    if override_plate is not None:
        plate_raw, confidence = override_plate, (override_confidence or 0.9)
    else:
        plate_raw, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    recognized_plate = ai_service.normalize_plate(plate_raw)
    valid_plate = ai_service.is_valid_vn_plate(recognized_plate)
    threshold = get_system_config_value(db, "plate_confidence_threshold", 0.6)
    rfid_card, rfid_error = validate_rfid_for_scan(db, trigger_type, rfid_tag, recognized_plate, gate_type)
    if rfid_error:
        return schemas.GateScanResponse(
            action="ignore",
            gate_type=gate_type,
            trigger_type=trigger_type,
            recognized_plate=recognized_plate or "UNKNOWN",
            confidence=confidence,
            valid_plate=valid_plate,
            matched=False,
            message=rfid_error,
        )
    rfid_card_type = rfid_card.card_type if rfid_card else None

    if existing_image_path:
        image_path = existing_image_path
    else:
        image_path = save_upload_image(image_bytes, filename)
    image_url = image_url_from_path(image_path)
    now = get_vietnam_now()

    if gate_type == "entry":
        vehicle_type, vehicle_msg = resolve_vehicle_type(db, recognized_plate)
        
        # Logic mới: Bắt buộc phải có thẻ RFID (đối với khách hoặc thẻ tháng) mới cho vào
        # Trừ trường hợp manual (bảo vệ mở bằng tay)
        has_rfid = rfid_tag is not None and len(rfid_tag.strip()) > 0
        can_open = valid_plate and confidence >= threshold and (has_rfid or trigger_type == "manual")
        
        action = "open" if can_open else "ignore"
        if not has_rfid and trigger_type != "manual":
            vehicle_msg = "Vui lòng quẹt thẻ RFID để gán cho biển số này"

        # Kiểm tra giới hạn sức chứa bãi xe
        if action == "open":
            duplicate_open_session = (
                db.query(models.ParkingSession)
                .filter(
                    models.ParkingSession.plate_number == recognized_plate,
                    models.ParkingSession.time_out.is_(None),
                    models.ParkingSession.match_status != "ignored",
                )
                .order_by(models.ParkingSession.time_in.desc())
                .first()
            )
            if duplicate_open_session and trigger_type != "manual":
                action = "ignore"
                can_open = False
                vehicle_msg = f"Biển số {recognized_plate} đang có phiên trong bãi, không cho vào thêm."

        if action == "open":
            guest_count, monthly_count = count_open_sessions_by_ticket_type(db)
            target_type = rfid_card_type or vehicle_type
            if target_type == "monthly":
                max_slots = int(get_system_config_value(db, "max_monthly_slots", get_system_config_value(db, "max_parking_slots", 50)))
                active_vehicles_count = monthly_count
            else:
                max_slots = int(get_system_config_value(db, "max_guest_slots", get_system_config_value(db, "max_parking_slots", 50)))
                active_vehicles_count = guest_count

            capacity = build_capacity_status(active_vehicles_count, max_slots)
            if capacity["capacity_status"] == "full":
                # Nếu không phải manual trigger thì chặn mở barrier
                if trigger_type != "manual":
                    action = "ignore"
                    can_open = False
                    vehicle_msg = capacity["capacity_message"]

        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == recognized_plate)
            .first()
        )

        # Chỉ tạo ParkingSession khi thực sự mở cổng (action="open")
        # Tránh tạo session "ma" khi bị từ chối, làm sai thống kê Dashboard
        if action == "open":
            session = models.ParkingSession(
                vehicle_id=vehicle.id if vehicle else None,
                plate_number=recognized_plate or "UNKNOWN",
                time_in=now,
                time_out=None,
                fee=0,
                image_path=image_path,
                gate_type="entry",
                trigger_type=trigger_type,
                trigger_source_id=source_id,
                rfid_tag=rfid_tag,
                rfid_card_id=rfid_card.id if rfid_card else None,
                rfid_card_type=rfid_card_type,
                plate_in=recognized_plate or "UNKNOWN",
                confidence_in=confidence,
                match_status="pending",
            )
            db.add(session)
            
            # Cập nhật trạng thái thẻ RFID thành "in_use" (Fix #6)
            if rfid_card:
                rfid_card.status = "in_use"
            
            db.commit()
            db.refresh(session)

            await notify_clients("parking_update", {
                "action": "open",
                "gate_type": "entry",
                "plate": recognized_plate,
                "session_id": session.id,
                "rfid_tag": rfid_tag,
                "confidence": confidence,
                "image_url": image_url,
                "message": vehicle_msg,
            })

            return schemas.GateScanResponse(
                action="open",
                gate_type="entry",
                trigger_type=trigger_type,
                rfid_card_type=rfid_card_type,
                plate_in=session.plate_in,
                recognized_plate=recognized_plate or "UNKNOWN",
                confidence=confidence,
                valid_plate=valid_plate,
                matched=True,
                session_id=session.id,
                rfid_tag=rfid_tag,
                image_url=image_url,
                message=vehicle_msg,
            )
        else:
            # Entry bị từ chối → KHÔNG tạo session, chỉ thông báo
            ignore_msg = vehicle_msg or "Không đủ điều kiện mở cổng"
            await notify_clients("parking_update", {
                "action": "ignore",
                "gate_type": "entry",
                "plate": recognized_plate,
                "rfid_tag": rfid_tag,
                "confidence": confidence,
                "image_url": image_url,
                "message": ignore_msg,
            })

            return schemas.GateScanResponse(
                action="ignore",
                gate_type="entry",
                trigger_type=trigger_type,
                rfid_card_type=rfid_card_type,
                recognized_plate=recognized_plate or "UNKNOWN",
                confidence=confidence,
                valid_plate=valid_plate,
                matched=False,
                rfid_tag=rfid_tag,
                image_url=image_url,
                message=ignore_msg,
            )

    # EXIT LOGIC: Tìm phiên theo RFID trước (Luồng: Quẹt thẻ để ra)
    open_session = None
    if rfid_tag:
        open_session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.rfid_tag == rfid_tag,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )
    
    # Nếu không tìm thấy bằng RFID, thử tìm bằng biển số (Dự phòng)
    if not open_session:
        open_session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.plate_number == recognized_plate,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )

    # Nếu là thẻ tháng và không tìm thấy open_session bằng RFID/recognized_plate (vd biển mờ/UNKNOWN), thử tìm bằng biển số đăng ký
    if not open_session and rfid_card and rfid_card.card_type == "monthly" and rfid_card.vehicle:
        registered_plate = ai_service.normalize_plate(rfid_card.vehicle.plate_number)
        open_session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.plate_number == registered_plate,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )

    # Cho phép ra bằng thẻ RFID nếu có phiên mở tương ứng:
    # - Biển số mờ/UNKNOWN/không hợp lệ nhưng RFID có session mở → cho ra (camera lỗi hoàn toàn)
    # - Biển số nhận SAI nhưng thẻ RFID khớp session entry VÀ sai lệch ≤ 3 ký tự → cho ra
    # - Biển số sai > 3 ký tự → từ chối dù RFID đúng (buộc bảo vệ force checkout, phòng gian lận)
    is_rfid_exit_allowed = False
    rfid_exit_reason = None
    allow_rfid_only_exit = get_config_bool(db, "allow_rfid_only_exit", True)
    if open_session and rfid_tag:
        if not valid_plate or confidence < threshold or recognized_plate == "UNKNOWN":
            # Camera hoàn toàn không đọc được biển → ưu tiên RFID
            if allow_rfid_only_exit:
                is_rfid_exit_allowed = True
                rfid_exit_reason = "unreadable"
                logger.info(f"Cho phép xe ra bằng thẻ RFID mặc dù biển số không hợp lệ/mờ: {recognized_plate}")
        elif rfid_card and open_session.rfid_card_id and open_session.rfid_card_id == rfid_card.id:
            # Thẻ RFID khớp chính xác session entry → kiểm tra mức sai lệch biển số
            rfid_plate_distance = levenshtein_distance(
                ai_service.normalize_plate(open_session.plate_number),
                recognized_plate
            )
            MAX_RFID_FALLBACK_DISTANCE = 3  # Cho phép sai tối đa 3 ký tự khi RFID đúng
            if 1 < rfid_plate_distance <= MAX_RFID_FALLBACK_DISTANCE:
                is_rfid_exit_allowed = True
                rfid_exit_reason = "rfid_assisted"
                logger.info(f"Cho phép xe ra: RFID khớp session entry (card_id={rfid_card.id}), biển số sai {rfid_plate_distance} ký tự (≤{MAX_RFID_FALLBACK_DISTANCE}): {recognized_plate} vs {open_session.plate_number}")
            elif rfid_plate_distance > MAX_RFID_FALLBACK_DISTANCE:
                logger.warning(f"TỪ CHỐI xe ra: RFID đúng nhưng biển số sai quá nhiều ({rfid_plate_distance} ký tự > {MAX_RFID_FALLBACK_DISTANCE}): {recognized_plate} vs {open_session.plate_number}. Yêu cầu bảo vệ force checkout.")

    plate_in_image_url = image_url_from_path(open_session.image_path) if open_session else None

    if (not valid_plate or confidence < threshold) and not is_rfid_exit_allowed:
        msg = MSG_RFID_ONLY_EXIT_DISABLED if open_session and rfid_tag and not allow_rfid_only_exit else "Biển số ra không hợp lệ hoặc ảnh mờ"
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": recognized_plate or "UNKNOWN",
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            plate_out=recognized_plate or "UNKNOWN",
            recognized_plate=recognized_plate or "UNKNOWN",
            confidence=confidence,
            valid_plate=valid_plate,
            matched=False,
            image_url=image_url,
            plate_in_image_url=plate_in_image_url,
            message=msg,
        )

    if not open_session:
        msg = "Không tìm thấy thông tin xe vào (Thẻ này chưa được dùng)"
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": recognized_plate,
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            rfid_card_type=rfid_card_type,
            plate_out=recognized_plate,
            recognized_plate=recognized_plate,
            confidence=confidence,
            valid_plate=True,
            matched=False,
            image_url=image_url,
            plate_in_image_url=plate_in_image_url,
            message=msg,
        )

    # So sánh Biển số ra với Biển số lúc vào
    if is_rfid_exit_allowed:
        plate_distance = 0
    else:
        plate_distance = levenshtein_distance(
            ai_service.normalize_plate(open_session.plate_number),
            recognized_plate
        )
        
    MAX_PLATE_DISTANCE = 1  # Cho phép tối đa sai 1 ký tự
    if plate_distance > MAX_PLATE_DISTANCE and not is_rfid_exit_allowed:
        msg = f"Biển số ra ({recognized_plate}) KHÔNG KHỚP với biển lúc vào ({open_session.plate_number})! (sai {plate_distance} ký tự)"
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": recognized_plate,
            "session_id": open_session.id,
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            rfid_card_type=rfid_card_type,
            plate_in=open_session.plate_number,
            plate_out=recognized_plate,
            recognized_plate=recognized_plate,
            confidence=confidence,
            valid_plate=True,
            matched=False,
            image_url=image_url,
            plate_in_image_url=plate_in_image_url,
            message=msg,
        )

    if trigger_type == "rfid" and open_session.rfid_card_id and rfid_card and open_session.rfid_card_id != rfid_card.id:
        msg = "Thẻ RFID này không khớp với thẻ lúc vào của xe này"
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": recognized_plate,
            "session_id": open_session.id,
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            rfid_card_type=rfid_card_type,
            plate_out=recognized_plate,
            recognized_plate=recognized_plate,
            confidence=confidence,
            valid_plate=True,
            matched=False,
            session_id=open_session.id,
            image_url=image_url,
            plate_in_image_url=plate_in_image_url,
            message=msg,
        )

    # Xác định loại vé để tính phí (xe tháng -> miễn phí)
    ticket_type = resolve_session_ticket_type(db, open_session)
    duration_minutes, fee = calculate_fee(now, open_session, db, ticket_type=ticket_type)

    # Chỉ cập nhật các trường exit, GIỮ NGUYÊN data entry gốc
    open_session.time_out = now
    open_session.fee = fee
    # KHÔNG ghi đè gate_type, trigger_type, rfid_tag gốc của entry
    open_session.plate_out = recognized_plate
    open_session.confidence_out = confidence
    open_session.match_status = "rfid_only" if is_rfid_exit_allowed else ("matched" if plate_distance == 0 else "fuzzy_matched")

    # Cập nhật trạng thái thẻ RFID thành "available" khi ra thành công
    rfid_card_to_release = rfid_card or get_rfid_card(db, open_session.rfid_tag)
    if rfid_card_to_release:
        rfid_card_to_release.status = "available"

    db.commit()
    db.refresh(open_session)

    if rfid_exit_reason == "unreadable":
        success_msg = MSG_RFID_ONLY_EXIT
    elif rfid_exit_reason == "rfid_assisted":
        success_msg = "Biển số ra lệch nhẹ so với biển vào, RFID khớp nên cho phép xe ra."
    elif plate_distance == 0:
        success_msg = "Biển số ra trùng khớp biển vào, cho phép xe ra"
    else:
        success_msg = "Biển số ra khớp trong ngưỡng cho phép, cho phép xe ra"

    # Thông báo qua WebSocket
    await notify_clients("parking_update", {
        "action": "open",
        "gate_type": "exit",
        "plate": recognized_plate,
        "fee": fee,
        "session_id": open_session.id,
        "rfid_tag": rfid_tag or open_session.rfid_tag,
        "confidence": confidence,
        "plate_in": open_session.plate_in or open_session.plate_number,
        "plate_out": recognized_plate,
        "duration_minutes": duration_minutes,
        "matched": True,
        "image_url": image_url,
        "plate_in_image_url": plate_in_image_url,
        "message": success_msg
    })

    return schemas.GateScanResponse(
        action="open",
        gate_type="exit",
        trigger_type=trigger_type,
        rfid_card_type=rfid_card_type or open_session.rfid_card_type,
        plate_in=open_session.plate_in or open_session.plate_number,
        plate_out=recognized_plate,
        recognized_plate=recognized_plate,
        confidence=confidence,
        valid_plate=True,
        matched=True,
        session_id=open_session.id,
        duration_minutes=duration_minutes,
        fee=fee,
        rfid_tag=rfid_tag or open_session.rfid_tag,
        image_url=image_url,
        plate_in_image_url=plate_in_image_url,
        message=success_msg,
    )


def process_checkin_compat(
    db: Session,
    plate: str,
    confidence: float,
    direction: str,
    image_path: Optional[str] = None,
) -> schemas.ParkingCheckinResponse:
    plate_norm = ai_service.normalize_plate(plate)
    valid_plate = ai_service.is_valid_vn_plate(plate_norm)
    threshold = get_system_config_value(db, "plate_confidence_threshold", 0.6)
    vehicle_type, message = resolve_vehicle_type(db, plate_norm)

    action = "open" if valid_plate and confidence >= threshold else "ignore"
    
    session = None
    if action == "open":
        session = models.ParkingSession(
            plate_number=plate_norm or "UNKNOWN",
            time_in=get_vietnam_now(),
            fee=0,
            image_path=image_path,
            gate_type="entry" if direction == "in" else "exit",
            trigger_type="manual",
            plate_in=plate_norm or "UNKNOWN",
            confidence_in=confidence,
            match_status="pending",
        )
        vehicle = db.query(models.Vehicle).filter(models.Vehicle.plate_number == plate_norm).first()
        if vehicle:
            session.vehicle_id = vehicle.id
        db.add(session)
        db.commit()
        db.refresh(session)

    return schemas.ParkingCheckinResponse(
        action=action,
        plate=plate_norm or "UNKNOWN",
        confidence=confidence,
        valid_plate=valid_plate,
        vehicle_type=vehicle_type,
        message=message,
        session_id=session.id if session else None,
    )


@app.get("/health")
def health_check():
    return {"status": "ok", "time": get_vietnam_now().isoformat()}


@app.post("/api/gates/trigger", response_model=schemas.GateTriggerResponse)
def gate_trigger(payload: schemas.GateTriggerRequest, db: Session = Depends(get_db)):
    gate_type = payload.gate_type.lower()
    trigger_type = payload.trigger_type.lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    if trigger_type not in ["sensor", "rfid"]:
        raise HTTPException(status_code=400, detail="trigger_type must be sensor or rfid")

    rfid_card_type = None
    if trigger_type == "rfid":
        card = get_rfid_card(db, payload.rfid_tag)
        if not card:
            raise HTTPException(status_code=404, detail="Khong tim thay the RFID")
        if not card.is_active:
            raise HTTPException(status_code=400, detail="The RFID da bi khoa")
        if card.expired_at and card.expired_at < get_vietnam_now():
            raise HTTPException(status_code=400, detail="The RFID da het han")
        rfid_card_type = card.card_type

    return schemas.GateTriggerResponse(
        status="ok",
        gate_type=gate_type,
        trigger_type=trigger_type,
        source_id=payload.source_id,
        rfid_tag=payload.rfid_tag,
        rfid_card_type=rfid_card_type,
        message="Da nhan trigger, frontend co the bat dau mo camera de quet",
    )


@app.post("/api/gates/scan-from-cam", response_model=schemas.GateScanResponse)
async def gate_scan_from_cam(
    gate_type: str = Form("entry"),
    trigger_type: str = Form("sensor"),
    source_id: Optional[str] = Form(None),
    rfid_tag: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    image_bytes = camera_service.capture_image(gate_type)
    if not image_bytes:
        raise HTTPException(status_code=500, detail="Không thể lấy ảnh từ Camera")
    return await process_gate_scan(
        db=db, image_bytes=image_bytes, filename=f"auto_{gate_type}.jpg",
        gate_type=gate_type, trigger_type=trigger_type, source_id=source_id, rfid_tag=rfid_tag
    )

@app.post("/api/gates/scan", response_model=schemas.GateScanResponse)
async def gate_scan(
    file: UploadFile = File(...),
    gate_type: str = Form("entry"),
    trigger_type: str = Form("sensor"),
    source_id: Optional[str] = Form(None),
    rfid_tag: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")
    return await process_gate_scan(
        db=db, image_bytes=image_bytes, filename=file.filename,
        gate_type=gate_type, trigger_type=trigger_type, source_id=source_id, rfid_tag=rfid_tag
    )


@app.post("/api/gates/sensor-event")
async def gate_sensor_event(payload: schemas.GateTriggerRequest, db: Session = Depends(get_db)):
    gate_type = payload.gate_type.lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")

    direction = "in" if gate_type == "entry" else "out"
    scan_token = uuid.uuid4().hex
    device_id = payload.source_id or f"{gate_type}-sensor-ui"

    try:
        db.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).delete()
        pending = models.PendingScan(
            gate_type=gate_type,
            plate_number="PROCESSING",
            confidence=0.0,
            image_path=None,
            device_id=device_id,
            scan_token=scan_token,
        )
        db.add(pending)
        db.commit()
    except Exception as e:
        logger.error(f"Error inserting PROCESSING pending scan from UI sensor: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Khong the tao phien quet cam bien")

    asyncio.create_task(
        bg_process_esp_event(
            direction=direction,
            gate_type=gate_type,
            device_id=device_id,
            scan_token=scan_token,
        )
    )

    await notify_clients("pending_scan", {
        "gate_type": gate_type,
        "recognized_plate": "PROCESSING",
        "confidence": 0.0,
        "message": "Đang bám biển số, vui lòng giữ xe trong vùng camera...",
    })

    return {
        "status": "processing",
        "gate_type": gate_type,
        "direction": direction,
        "scan_token": scan_token,
        "message": "Đã kích hoạt cảm biến giả lập, hệ thống đang bám biển số.",
    }


# ============ ESP32 ENDPOINTS ============
@app.post("/api/esp/register")
def register_esp_ip(request: Request):
    """
    ESP32 gui thong tin IP len Backend khi khoi dong xong hoac ket noi lai Wi-Fi.
    """
    global esp32_ip
    esp32_ip = request.client.host
    logger.info(f"ESP32 registered IP address: {esp32_ip}")
    return {"status": "ok", "esp32_ip": esp32_ip, "message": "Dang ky IP thanh cong"}


# Cooldown: tránh xử lý event trùng lặp từ cảm biến IR
_esp_event_cooldown = {}  # {"in": timestamp, "out": timestamp}
ESP_EVENT_COOLDOWN_SECONDS = 2  # Bỏ qua event cùng hướng trong 2 giây
PLATE_SCAN_WINDOW_SECONDS = 3.0
PLATE_SCAN_INTERVAL_SECONDS = 0.35
MANUAL_GATE_OPEN_SECONDS = 5.0
_manual_gate_open_until = {"entry": 0.0, "exit": 0.0}

MSG_GATE_OPEN_WAIT = "Cổng {gate_type} đang mở, vui lòng đợi {remaining}s trước khi gửi lệnh tiếp."
MSG_MANUAL_OPEN_MQTT = "Đã mở cổng thủ công thành công qua MQTT."
MSG_MANUAL_OPEN_HTTP = "Mở cổng {gate_type} thủ công từ xa thành công."
MSG_RFID_ONLY_EXIT = "Camera không đọc được biển số, hệ thống cho ra theo RFID dự phòng."
MSG_RFID_ONLY_EXIT_DISABLED = "Camera không đọc được biển số. Chế độ cho ra dự phòng bằng RFID đang tắt."
FIRE_GATE_OPEN_COOLDOWN_SECONDS = 30.0
_last_fire_gate_open_at = 0.0

# Hàng đợi tạm thời chứa các thẻ RFID quét trước khi AI nhận dạng biển số xong
# Định dạng: { gate_type: (uid_norm, device_id, swipe_time) }
_pending_rfid_scans = {}

async def process_mqtt_rfid_validation(db: Session, pending, uid_norm: str, gate_type: str, device_id: str, direction: str):
    recognized_plate = pending.plate_number
    image_path = pending.image_path
    confidence = pending.confidence

    result = await process_gate_scan(
        db=db,
        image_bytes=None,
        filename=None,
        gate_type=gate_type,
        trigger_type="rfid",
        source_id=device_id,
        rfid_tag=uid_norm,
        override_plate=recognized_plate,
        override_confidence=confidence,
        existing_image_path=image_path,
    )

    if result.action == "open":
        mqtt_manager.publish_open_gate(device_id, direction)

    await notify_clients("parking_update", {
        "action": result.action,
        "gate_type": gate_type,
        "plate": result.recognized_plate,
        "plate_in": result.plate_in,
        "plate_out": result.plate_out,
        "session_id": result.session_id,
        "rfid_tag": uid_norm,
        "confidence": result.confidence,
        "duration_minutes": result.duration_minutes,
        "fee": result.fee,
        "matched": result.matched,
        "image_url": result.image_url,
        "plate_in_image_url": result.plate_in_image_url,
        "message": result.message,
    })

    should_delete_pending = (
        result.action == "open" or 
        not result.valid_plate or 
        (result.message and "không hợp lệ" in result.message) or 
        (result.message and "ảnh mờ" in result.message) or
        (result.message and "đang được sử dụng" in result.message) or
        (result.message and "het han" in result.message.lower()) or
        (result.message and "khong khop" in result.message.lower()) or
        (result.message and "khong tim thay" in result.message.lower()) or
        (result.message and "da bi khoa" in result.message.lower())
    )
    if should_delete_pending:
        db.delete(pending)
        db.commit()

async def handle_mqtt_event(device_id: str, event_type: str, payload: dict):
    """
    Xử lý các sự kiện bất đồng bộ từ ESP32 qua giao thức MQTT.
    """
    db = SessionLocal()
    try:
        if event_type == "car_detected":
            direction = payload.get("direction", "in")
            gate_type = "entry" if direction == "in" else "exit"
            now = time_module.time()

            # Kiểm tra cooldown
            last_time = _esp_event_cooldown.get(direction, 0)
            if now - last_time < ESP_EVENT_COOLDOWN_SECONDS:
                logger.info(f"MQTT IR Event {direction} ignored due to cooldown.")
                return

            _esp_event_cooldown[direction] = now
            scan_token = uuid.uuid4().hex

            # Đăng ký trạng thái PROCESSING vào database
            try:
                db.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).delete()
                pending = models.PendingScan(
                    gate_type=gate_type,
                    plate_number="PROCESSING",
                    confidence=0.0,
                    image_path=None,
                    device_id=device_id,
                    scan_token=scan_token
                )
                db.add(pending)
                db.commit()
            except Exception as e:
                logger.error(f"Error inserting PROCESSING pending scan in MQTT: {e}")
                db.rollback()
                return

            # Chạy trực tiếp bg_process_esp_event như một task bất đồng bộ trong event loop của FastAPI
            asyncio.create_task(
                bg_process_esp_event(
                    direction=direction,
                    gate_type=gate_type,
                    device_id=device_id,
                    scan_token=scan_token
                )
            )

        elif event_type == "rfid_scan":
            uid = payload.get("uid", "")
            direction_hint = payload.get("direction", "in")
            gate_id = payload.get("gate_id", "gate_in")
            
            uid_norm = uid.strip().upper().replace(" ", "").replace(":", "")
            if not uid_norm:
                return

            # Tự động import thẻ nếu trong whitelist cấu hình
            card = get_rfid_card(db, uid_norm)
            if not card:
                whitelist_raw = get_config_text(db, "rfid_uid_whitelist", "")
                whitelist = {
                    item.strip().upper().replace(" ", "")
                    for item in whitelist_raw.split(",")
                    if item.strip()
                }
                if uid_norm in whitelist:
                    card = models.RFIDCard(
                        card_uid=uid_norm,
                        card_type="guest",
                        is_active=True,
                    )
                    db.add(card)
                    db.commit()
                    db.refresh(card)

            # Xác định hướng logic dựa trên session mở trong DB
            open_session = (
                db.query(models.ParkingSession)
                .filter(
                    models.ParkingSession.rfid_tag == uid_norm,
                    models.ParkingSession.time_out.is_(None),
                )
                .order_by(models.ParkingSession.time_in.desc())
                .first()
            )
            
            # Thẻ tháng dự phòng
            if not open_session and card and card.card_type == "monthly" and card.vehicle:
                registered_plate = ai_service.normalize_plate(card.vehicle.plate_number)
                open_session = (
                    db.query(models.ParkingSession)
                    .filter(
                        models.ParkingSession.plate_number == registered_plate,
                        models.ParkingSession.time_out.is_(None),
                    )
                    .order_by(models.ParkingSession.time_in.desc())
                    .first()
                )

            logical_direction = "out" if open_session else "in"

            # Xác định cổng thực tế
            pending_entry = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
            pending_exit = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "exit").first()
            
            now_dt = get_vietnam_now()
            EXPIRE_SECONDS = 45
            
            active_entry = pending_entry if (pending_entry and (now_dt - pending_entry.created_at).total_seconds() <= EXPIRE_SECONDS) else None
            active_exit = pending_exit if (pending_exit and (now_dt - pending_exit.created_at).total_seconds() <= EXPIRE_SECONDS) else None

            resolved_gate_type = None
            if active_entry and not active_exit:
                resolved_gate_type = "entry"
            elif active_exit and not active_entry:
                resolved_gate_type = "exit"
            elif active_entry and active_exit:
                resolved_gate_type = "entry" if logical_direction == "in" else "exit"
            else:
                resolved_gate_type = "entry" if direction_hint == "in" else "exit"

            direction = "in" if resolved_gate_type == "entry" else "out"
            gate_type = resolved_gate_type
            
            pending = active_entry if gate_type == "entry" else active_exit

            if not pending and gate_type == "entry" and card and card.status == "in_use":
                await notify_clients("parking_update", {
                    "action": "ignore",
                    "gate_type": "entry",
                    "plate": "UNKNOWN",
                    "rfid_tag": uid_norm,
                    "confidence": 0.0,
                    "matched": False,
                    "message": "Thẻ RFID đang được sử dụng bởi xe khác",
                })
                return

            # Nếu là cổng ra dự phòng: không có pending scan nhưng thẻ có session mở -> Cho ra luôn
            if not pending and gate_type == "exit" and open_session:
                result = await process_gate_scan(
                    db=db,
                    image_bytes=None,
                    filename=None,
                    gate_type=gate_type,
                    trigger_type="rfid",
                    source_id=device_id,
                    rfid_tag=uid_norm,
                    override_plate="UNKNOWN",
                    override_confidence=0.0,
                    existing_image_path=None,
                )
                if result.action == "open":
                    mqtt_manager.publish_open_gate(device_id, direction)
                await notify_clients("parking_update", {
                    "action": result.action,
                    "gate_type": gate_type,
                    "plate": result.recognized_plate,
                    "plate_in": result.plate_in,
                    "plate_out": result.plate_out,
                    "session_id": result.session_id,
                    "rfid_tag": uid_norm,
                    "confidence": result.confidence,
                    "duration_minutes": result.duration_minutes,
                    "fee": result.fee,
                    "matched": result.matched,
                    "image_url": result.image_url,
                    "plate_in_image_url": result.plate_in_image_url,
                    "message": result.message,
                })
                return

            if not pending:
                await notify_clients("parking_update", {
                    "action": "ignore",
                    "gate_type": gate_type,
                    "plate": "UNKNOWN",
                    "confidence": 0.0,
                    "message": "Vui lòng đỗ xe đúng vị trí cảm biến trước khi quẹt thẻ",
                })
                return

            # Nếu AI vẫn đang PROCESSING -> Đưa vào hàng chờ quẹt sớm
            if pending.plate_number == "PROCESSING":
                logger.info(f"RFID early swipe detected for {gate_type}. Storing in _pending_rfid_scans.")
                _pending_rfid_scans[gate_type] = (uid_norm, device_id, now_dt)
                await notify_clients("pending_scan", {
                    "gate_type": gate_type,
                    "recognized_plate": "PROCESSING",
                    "confidence": 0.0,
                    "message": "Đang nhận dạng biển số, vui lòng giữ nguyên vị trí, cổng sẽ mở tự động..."
                })
                return

            # Nếu đã xử lý xong AI, gọi hàm validation bình thường
            await process_mqtt_rfid_validation(db, pending, uid_norm, gate_type, device_id, direction)

        elif event_type == "fire_alert":
            sensor_value = payload.get("sensor_value", 0)
            message = payload.get("message", "Fire sensor triggered")
            alert = models.FireAlert(
                sensor_id=device_id,
                level="critical",
                message=message or f"Fire sensor triggered (value={sensor_value})",
            )
            db.add(alert)
            set_fire_alarm_active(db, True)
            db.commit()
            db.refresh(alert)
            gate_opened = handle_critical_fire_gate_open()
            
            await notify_clients("fire_alert", {
                "id": alert.id,
                "sensor_id": alert.sensor_id,
                "message": alert.message,
                "timestamp": alert.created_at.isoformat(),
                "gate_opened": gate_opened,
            })

    except Exception as e:
        logger.error(f"Lỗi khi xử lý handle_mqtt_event: {e}")
    finally:
        db.close()

async def bg_process_esp_event(
    direction: str,
    gate_type: str,
    device_id: Optional[str],
    scan_token: str
):
    """
    Xử lý chụp ảnh và nhận diện biển số bất đồng bộ trong background task.
    Giúp giải phóng luồng chính của ESP32 ngay lập tức để không bị lỗi timeout (-11)
    và luôn sẵn sàng đọc thẻ RFID.
    """
    # 1. Chụp ảnh từ Webcam & Nhận diện (thực hiện song song, không khóa event loop/DB)
    threshold = 0.6
    db_for_threshold = SessionLocal()
    try:
        threshold = get_system_config_value(db_for_threshold, "plate_confidence_threshold", 0.6)
    finally:
        db_for_threshold.close()

    plate_tracker.start(gate_type, PLATE_SCAN_WINDOW_SECONDS)
    best_image_bytes = None
    best_plate_raw = "UNKNOWN"
    best_confidence = 0.0
    best_valid = False
    best_bbox = None
    last_progress_sent_at = 0.0
    deadline = time_module.time() + PLATE_SCAN_WINDOW_SECONDS
    attempt = 0

    while time_module.time() <= deadline:
        attempt += 1
        image_bytes = camera_service.capture_image(gate_type)
        if image_bytes:
            track_result = plate_tracker.update(gate_type, image_bytes, threshold)
            plate_raw = track_result.get("best_plate") or "UNKNOWN"
            confidence = float(track_result.get("best_confidence") or 0.0)
            normalized = ai_service.normalize_plate(plate_raw)
            valid_plate = ai_service.is_valid_vn_plate(normalized)

            now_progress = time_module.time()
            if now_progress - last_progress_sent_at >= 0.7:
                last_progress_sent_at = now_progress
                await notify_clients("tracking_update", {
                    "gate_type": gate_type,
                    "status": track_result.get("status", "tracking"),
                    "attempts": track_result.get("attempts", attempt),
                    "plate": normalized or "UNKNOWN",
                    "confidence": confidence,
                    "stable_count": track_result.get("stable_count", 0),
                    "bbox": track_result.get("bbox"),
                    "message": "Đang bám biển số, chờ frame rõ..."
                })

            if track_result.get("accepted") and valid_plate and confidence >= threshold:
                best_image_bytes = track_result.get("best_image_bytes") or image_bytes
                best_plate_raw = plate_raw
                best_confidence = confidence
                best_valid = True
                best_bbox = track_result.get("best_bbox") or track_result.get("bbox")
                logger.info(
                    "Plate scan accepted for %s after %s attempt(s): plate=%s confidence=%.3f",
                    gate_type,
                    attempt,
                    normalized,
                    confidence,
                )
                break

            if confidence > best_confidence or (valid_plate and not best_valid):
                best_image_bytes = track_result.get("best_image_bytes") or image_bytes
                best_plate_raw = plate_raw
                best_confidence = confidence
                best_valid = valid_plate
                best_bbox = track_result.get("best_bbox") or track_result.get("bbox")

        await asyncio.sleep(PLATE_SCAN_INTERVAL_SECONDS)

    if best_image_bytes is None:
        best_plate_raw = "UNKNOWN"
        best_confidence = 0.0

        import numpy as np
        import cv2
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.putText(dummy_img, "NO CAMERA", (5, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        _, buffer = cv2.imencode('.jpg', dummy_img)
        best_image_bytes = buffer.tobytes()

    plate_raw, confidence = best_plate_raw, best_confidence
    image_bytes = best_image_bytes
    recognized_plate = ai_service.normalize_plate(plate_raw)
    plate_tracker.stop(gate_type, "accepted" if best_valid and confidence >= threshold else "finished")
    evidence_image_bytes = crop_image_bytes_by_bbox(image_bytes, best_bbox) or image_bytes
    image_path = save_upload_image(evidence_image_bytes, f"esp_event_{direction}.jpg")

    # 2. Sử dụng lock và kiểm tra token để tránh overwrite race condition và SQLite block
    async with gate_locks[gate_type]:
        db_session = SessionLocal()
        try:
            # Kiểm tra xem có bị overwrite bởi event mới hơn không
            pending = db_session.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).first()
            if not pending or pending.scan_token != scan_token:
                logger.info(f"Background task for {gate_type} superseded. Discarding results.")
                return

            valid_plate = ai_service.is_valid_vn_plate(recognized_plate)
            threshold = get_system_config_value(db_session, "plate_confidence_threshold", 0.6)

            # Ở làn vào, nếu biển số không hợp lệ/mờ/UNKNOWN -> Không tạo hàng đợi chờ quẹt thẻ, yêu cầu quét lại ngay
            if gate_type == "entry" and (not valid_plate or confidence < threshold or recognized_plate == "UNKNOWN"):
                db_session.delete(pending)
                db_session.commit()
                
                msg = "Biển số vào không hợp lệ hoặc ảnh mờ. Vui lòng quét lại."
                await notify_clients("parking_update", {
                    "action": "ignore",
                    "gate_type": "entry",
                    "plate": recognized_plate or "UNKNOWN",
                    "confidence": confidence,
                    "image_url": image_url_from_path(image_path),
                    "message": msg,
                })
                return

            # Đưa thông tin vào hàng đợi tạm chờ quẹt thẻ (Cập nhật bản ghi PROCESSING hiện có)
            pending.plate_number = recognized_plate
            pending.confidence = confidence
            pending.image_path = image_path
            db_session.commit()
            
            # Gửi WebSocket báo cho Frontend cập nhật UI
            await notify_clients("pending_scan", {
                "gate_type": gate_type,
                "recognized_plate": recognized_plate,
                "confidence": confidence,
                "image_url": image_url_from_path(image_path),
                "message": "Chờ quẹt thẻ RFID..."
            })

            # Kiểm tra xem có thẻ RFID nào quét sớm đang đợi nhận diện biển số không
            pending_rfid = _pending_rfid_scans.pop(gate_type, None)
            if pending_rfid:
                uid_norm, device_id, swipe_time = pending_rfid
                # Chỉ xử lý nếu thời gian quẹt trong vòng 15 giây
                if (get_vietnam_now() - swipe_time).total_seconds() <= 15:
                    logger.info(f"Triggering deferred RFID validation for {gate_type} with card {uid_norm}")
                    direction = "in" if gate_type == "entry" else "out"
                    await process_mqtt_rfid_validation(db_session, pending, uid_norm, gate_type, device_id, direction)
                else:
                    logger.info(f"Deferred RFID scan for {gate_type} expired.")
        except Exception as e:
            logger.error(f"Lỗi khi xử lý background event: {e}")
            db_session.rollback()
            # Clean up if current pending is still ours
            try:
                p_check = db_session.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).first()
                if p_check and p_check.scan_token == scan_token:
                    db_session.delete(p_check)
                    db_session.commit()
            except Exception as clean_err:
                logger.error(f"Lỗi clean up pending scan: {clean_err}")
        finally:
            db_session.close()

@app.post("/api/esp/events", response_model=schemas.EspEventResponse)
async def handle_esp_event(
    payload: schemas.EspEventRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    ESP32 gui tin hieu xe den (IR Sensor). 
    Backend tu dong chup anh tu Webcam, nhan dien va dua vao hang doi pending_gates.
    """
    global esp32_ip
    esp32_ip = request.client.host
    
    direction = payload.direction or "in"
    gate_type = "entry" if direction == "in" else "exit"
    now = time_module.time()
    
    # Kiểm tra cooldown
    last_time = _esp_event_cooldown.get(direction, 0)
    if now - last_time < ESP_EVENT_COOLDOWN_SECONDS:
        remaining = round(ESP_EVENT_COOLDOWN_SECONDS - (now - last_time), 1)
        return schemas.EspEventResponse(
            action="cooldown",
            plate="",
            vehicle_type="",
            message=f"Cooldown {remaining}s. Vui long doi.",
        )
    
    _esp_event_cooldown[direction] = now
    
    # Tạo scan_token duy nhất cho phiên quét này
    scan_token = uuid.uuid4().hex
    
    # Đăng ký trạng thái PROCESSING vào database trước khi spawn background task
    try:
        db.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).delete()
        pending = models.PendingScan(
            gate_type=gate_type,
            plate_number="PROCESSING",
            confidence=0.0,
            image_path=None,
            device_id=payload.device_id,
            scan_token=scan_token
        )
        db.add(pending)
        db.commit()
    except Exception as e:
        logger.error(f"Error inserting PROCESSING pending scan: {e}")
        db.rollback()
    
    # 1. Xac dinh camera can chup
    # 2. Đưa tác vụ chụp ảnh và nhận diện biển số vào Background Tasks để tránh block ESP32
    background_tasks.add_task(
        bg_process_esp_event,
        direction=direction,
        gate_type=gate_type,
        device_id=payload.device_id,
        scan_token=scan_token
    )
    
    return schemas.EspEventResponse(
        action="ignore",
        plate="PROCESSING",
        vehicle_type="processing",
        message="Đang xử lý nhận dạng biển số trong nền...",
    )


@app.post("/api/esp/manual-open")
def handle_manual_open(payload: schemas.ManualOpenRequest):
    return {
        "status": "ok",
        "device_id": payload.device_id,
        "reason": payload.reason,
        "time": get_vietnam_now().isoformat(),
    }


@app.post("/api/gates/force-open")
async def force_open_gate(
    gate_type: str = Form(...),
    reason: str = Form("manual_override"),
    operator: str = Form("operator"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Gui lenh mo cong thu cong tu Web UI toi ESP32.
    Neu cong dang trong thoi gian mo thu cong thi khong gui lenh lap lai.
    """
    gate_type = (gate_type or "").lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")

    gate = "in" if gate_type == "entry" else "out"
    manual_gate_open_seconds = get_system_config_value(db, "manual_gate_open_seconds", MANUAL_GATE_OPEN_SECONDS)
    now = time_module.time()
    open_until = _manual_gate_open_until.get(gate_type, 0.0)
    if now < open_until:
        remaining = max(1, int(open_until - now + 0.999))
        message = MSG_GATE_OPEN_WAIT.format(gate_type=gate_type, remaining=remaining)
        await notify_clients("parking_update", {
            "action": "gate_open",
            "gate_type": gate_type,
            "message": message,
        })
        return {
            "status": "gate_open",
            "gate_type": gate_type,
            "remaining_seconds": remaining,
            "message": message,
        }

    if mqtt_manager.is_connected:
        mqtt_manager.publish_open_gate("esp32-barrier-01", gate)
        _manual_gate_open_until[gate_type] = time_module.time() + manual_gate_open_seconds
        create_manual_gate_log(db, gate_type, "open_manual", reason=reason, operator=operator, source="web_mqtt")
        message = MSG_MANUAL_OPEN_MQTT
        await notify_clients("parking_update", {
            "action": "open_manual",
            "gate_type": gate_type,
            "message": message,
        })
        return {"status": "ok", "message": message}

    global esp32_ip
    if not esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 chua ket noi hoac chua cap nhat IP len Backend."
        )

    esp_url = f"http://{esp32_ip}/open-gate?gate={gate}"

    import urllib.request
    import urllib.error
    from fastapi.concurrency import run_in_threadpool

    def send_http_request():
        try:
            req = urllib.request.Request(esp_url, method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as response:
                return response.getcode(), response.read().decode('utf-8')
        except urllib.error.URLError as e:
            return -1, str(e.reason)
        except Exception as e:
            return -1, str(e)

    code, body = await run_in_threadpool(send_http_request)

    if code == 200:
        _manual_gate_open_until[gate_type] = time_module.time() + manual_gate_open_seconds
        create_manual_gate_log(db, gate_type, "open_manual", reason=reason, operator=operator, source="web_http")
        message = MSG_MANUAL_OPEN_HTTP.format(gate_type=gate_type)
        await notify_clients("parking_update", {
            "action": "open_manual",
            "gate_type": gate_type,
            "message": message,
        })
        return {"status": "ok", "message": message}

    raise HTTPException(
        status_code=502,
        detail=f"Khong the ket noi hoac loi phan hoi tu ESP32: {body}"
    )


@app.get("/api/gates/manual-open-logs", response_model=List[schemas.ManualGateLog])
def list_manual_gate_logs(limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(models.ManualGateLog)
        .order_by(models.ManualGateLog.created_at.desc(), models.ManualGateLog.id.desc())
        .limit(limit)
        .all()
    )


@app.post("/api/esp/rfid", response_model=schemas.EspRfidResponse)
async def handle_esp_rfid(
    payload: schemas.EspRfidRequest,
    request: Request,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Xac thuc UID RFID tu ESP32, lay bien so dang cho tu pending_gates va thuc hien process_gate_scan.
    Tự động import thẻ nếu thẻ nằm trong whitelist cấu hình nhưng chưa có trong DB.
    """
    global esp32_ip
    esp32_ip = request.client.host
    
    uid_norm = payload.uid.strip().upper().replace(" ", "").replace(":", "")
    
    # 1. Tự động chuyển thẻ từ whitelist cấu hình vào DB nếu chưa tồn tại
    card = get_rfid_card(db, uid_norm)
    if not card:
        whitelist_raw = get_config_text(db, "rfid_uid_whitelist", "")
        whitelist = {
            item.strip().upper().replace(" ", "")
            for item in whitelist_raw.split(",")
            if item.strip()
        }
        if uid_norm in whitelist:
            card = models.RFIDCard(
                card_uid=uid_norm,
                card_type="guest",
                is_active=True,
            )
            db.add(card)
            db.commit()
            db.refresh(card)

    # 2. Xác định hướng logic dựa trên session mở trong DB (Smart direction detection)
    open_session = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.rfid_tag == uid_norm,
            models.ParkingSession.time_out.is_(None),
        )
        .order_by(models.ParkingSession.time_in.desc())
        .first()
    )
    
    # Nếu là thẻ tháng và không tìm thấy theo RFID tag, thử tìm theo biển số xe đăng ký
    if not open_session and card and card.card_type == "monthly" and card.vehicle:
        registered_plate = ai_service.normalize_plate(card.vehicle.plate_number)
        open_session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.plate_number == registered_plate,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )
        
    logical_direction = "out" if open_session else "in"

    # Kiểm tra hàng đợi quét biển số ở cả 2 hướng (< 45 giây)
    pending_entry = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
    pending_exit = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "exit").first()
    
    now_dt = get_vietnam_now()
    EXPIRE_SECONDS = 45
    
    active_entry = pending_entry if (pending_entry and (now_dt - pending_entry.created_at).total_seconds() <= EXPIRE_SECONDS) else None
    active_exit = pending_exit if (pending_exit and (now_dt - pending_exit.created_at).total_seconds() <= EXPIRE_SECONDS) else None
    
    # Giải quyết hướng thực tế dựa trên các queue có xe đang chờ
    resolved_gate_type = None
    if active_entry and not active_exit:
        resolved_gate_type = "entry"
    elif active_exit and not active_entry:
        resolved_gate_type = "exit"
    elif active_entry and active_exit:
        resolved_gate_type = "entry" if logical_direction == "in" else "exit"
    else:
        # Fallback về hướng payload gửi lên
        resolved_gate_type = "entry" if (payload.direction or "in") == "in" else "exit"

    direction = "in" if resolved_gate_type == "entry" else "out"
    gate_type = resolved_gate_type
    
    pending = active_entry if gate_type == "entry" else active_exit

    if not pending and gate_type == "entry" and card and card.status == "in_use":
        return schemas.EspRfidResponse(
            action="ignore",
            uid=uid_norm,
            message="Thẻ RFID đang được sử dụng bởi xe khác",
            direction=direction,
            gate_id=payload.gate_id,
        )

    # 3. Dự phòng cho cổng ra: nếu camera hỏng/không có pending_scan nhưng thẻ có open session -> Cho phép ra (UNKNOWN plate fallback)
    if not pending and gate_type == "exit" and open_session:
        result = await process_gate_scan(
            db=db,
            image_bytes=None,
            filename=None,
            gate_type=gate_type,
            trigger_type="rfid",
            source_id=payload.device_id,
            rfid_tag=uid_norm,
            override_plate="UNKNOWN",
            override_confidence=0.0,
            existing_image_path=None,
        )
        return schemas.EspRfidResponse(
            action=result.action,
            uid=uid_norm,
            message=result.message,
            direction=direction,
            gate_id=payload.gate_id,
        )

    if not pending:
        return schemas.EspRfidResponse(
            action="ignore",
            uid=uid_norm,
            message="Vui lòng đỗ xe đúng vị trí cảm biến trước khi quẹt thẻ",
            direction=direction,
            gate_id=payload.gate_id,
        )

    # 4. Nếu AI đang xử lý -> Trả thông báo chờ retry thay vì báo lỗi
    if pending.plate_number == "PROCESSING":
        return schemas.EspRfidResponse(
            action="ignore",
            uid=uid_norm,
            message="Đang nhận diện biển số, vui lòng đợi 2-3 giây rồi quẹt lại",
            direction=direction,
            gate_id=payload.gate_id,
        )

    recognized_plate = pending.plate_number
    image_path = pending.image_path
    confidence = pending.confidence

    # 5. Gọi process_gate_scan thực hiện logic
    result = await process_gate_scan(
        db=db,
        image_bytes=None,
        filename=None,
        gate_type=gate_type,
        trigger_type="rfid",
        source_id=payload.device_id,
        rfid_tag=uid_norm,
        override_plate=recognized_plate,
        override_confidence=confidence,
        existing_image_path=image_path,
    )

    # 6. Xóa biển số khỏi hàng đợi tạm nếu:
    #    - Mở cổng thành công (action="open")
    #    - Biển số không hợp lệ hoặc ảnh mờ
    #    - RFID bị reject (thẻ hết hạn, thẻ đang dùng, biển không khớp...)
    #      → Phải xóa pending scan để không ảnh hưởng xe tiếp theo
    should_delete_pending = (
        result.action == "open" or 
        not result.valid_plate or 
        (result.message and "không hợp lệ" in result.message) or 
        (result.message and "ảnh mờ" in result.message) or
        (result.message and "đang được sử dụng" in result.message) or
        (result.message and "het han" in result.message.lower()) or
        (result.message and "khong khop" in result.message.lower()) or
        (result.message and "khong tim thay" in result.message.lower()) or
        (result.message and "da bi khoa" in result.message.lower())
    )
    if should_delete_pending:
        db.delete(pending)
        db.commit()

    return schemas.EspRfidResponse(
        action=result.action,
        uid=uid_norm,
        message=result.message,
        direction=direction,
        gate_id=payload.gate_id,
    )


@app.post("/api/esp/fire-alert", response_model=schemas.FireAlertResponse)
async def handle_fire_alert(
    payload: schemas.FireAlertRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Nhan canh bao chay tu ESP32.
    Lưu vào DB và broadcast qua WebSocket.
    """
    # Lưu vào database
    alert = models.FireAlert(
        sensor_id=payload.device_id,
        level="critical",
        message=payload.message or f"Fire sensor triggered (value={payload.sensor_value})",
    )
    db.add(alert)
    set_fire_alarm_active(db, True)
    db.commit()
    db.refresh(alert)
    gate_opened = handle_critical_fire_gate_open()

    # Broadcast cảnh báo lên WebSocket
    await notify_clients("fire_alert", {
        "id": alert.id,
        "sensor_id": alert.sensor_id,
        "message": alert.message,
        "level": alert.level,
        "from_esp32": True,
        "gate_opened": gate_opened,
    })

    return schemas.FireAlertResponse(
        status="ok",
        action="open_all",
        message=payload.message or f"Fire alert from {payload.device_id}",
    )


# ============ CAMERA STREAMING ============

def gen_frames(gate_type: str):
    while camera_manager.is_running:
        frame_bytes = camera_manager.capture(gate_type)
        if frame_bytes:
            frame_bytes = plate_tracker.annotate_frame(gate_type, frame_bytes)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            time_module.sleep(0.5)
        time_module.sleep(0.04)  # ~25 FPS

@app.get("/api/camera/stream/{gate_type}")
def video_feed(gate_type: str):
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="Invalid gate type")
    return StreamingResponse(gen_frames(gate_type),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/camera/tracking-status/{gate_type}")
def tracking_status(gate_type: str):
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="Invalid gate type")
    return plate_tracker.snapshot(gate_type)


# ============ AI RECOGNIZE PLATE ============

@app.post("/api/ai/recognize-plate", response_model=schemas.PlateRecognitionResult)
async def recognize_plate_endpoint(file: UploadFile = File(...)):
    image_bytes = await file.read()
    plate, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    return schemas.PlateRecognitionResult(plate=plate, confidence=confidence)


# ============ BACKWARD-COMPAT WRAPPERS ============
@app.post("/api/parking/check-in", response_model=schemas.ParkingCheckinResponse)
async def parking_check_in(
    file: UploadFile = File(...),
    direction: str = Form("in"),
    device_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")

    gate_type = "entry" if direction == "in" else "exit"
    scan_result = await process_gate_scan(
        db=db,
        image_bytes=image_bytes,
        filename=file.filename,
        gate_type=gate_type,
        trigger_type="manual",
        source_id=device_id,
        rfid_tag=None,
    )

    return schemas.ParkingCheckinResponse(
        action=scan_result.action,
        plate=scan_result.recognized_plate,
        confidence=scan_result.confidence,
        valid_plate=scan_result.valid_plate,
        vehicle_type="guest",
        message=scan_result.message,
        session_id=scan_result.session_id,
    )


# ============ CRUD VEHICLE ============
@app.post("/api/vehicles", response_model=schemas.Vehicle, status_code=status.HTTP_201_CREATED)
def create_vehicle(vehicle_in: schemas.VehicleCreate, db: Session = Depends(get_db)):
    plate_norm = ai_service.normalize_plate(vehicle_in.plate_number)
    exists = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == plate_norm)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Bien so da ton tai")

    # Guest vehicles do not store owner identity fields.
    vehicle = models.Vehicle(
        plate_number=plate_norm,
        owner_name=None,
        phone=None,
        note=vehicle_in.note,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@app.get("/api/vehicles", response_model=List[schemas.Vehicle])
def list_vehicles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Vehicle).offset(skip).limit(limit).all()


@app.get("/api/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Khong tim thay xe")
    return vehicle


@app.patch("/api/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def update_vehicle(
    vehicle_id: int,
    vehicle_in: schemas.VehicleUpdate,
    db: Session = Depends(get_db),
):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Khong tim thay xe")

    for field, value in vehicle_in.dict(exclude_unset=True).items():
        setattr(vehicle, field, value)

    today = get_vietnam_date()
    active_sub = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.vehicle_id == vehicle.id,
            models.Subscription.is_active == True,  # noqa: E712
            models.Subscription.start_date <= today,
            models.Subscription.end_date >= today,
        )
        .first()
    )
    if active_sub and active_sub.monthly_user:
        vehicle.owner_name = active_sub.monthly_user.full_name
        vehicle.phone = active_sub.monthly_user.phone
    else:
        # Keep guest vehicle owner identity empty.
        vehicle.owner_name = None
        vehicle.phone = None

    db.commit()
    db.refresh(vehicle)
    return vehicle


@app.delete("/api/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Khong tim thay xe")
    db.delete(vehicle)
    db.commit()
    return


# ============ SUBSCRIPTIONS ============
@app.post("/api/subscriptions", response_model=schemas.Subscription)
def create_subscription(sub_in: schemas.SubscriptionCreate, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(sub_in.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Xe khong ton tai")

    monthly_user = db.query(models.MonthlyUser).get(sub_in.monthly_user_id)
    if not monthly_user:
        raise HTTPException(status_code=404, detail="Chu xe ve thang khong ton tai")

    # Monthly registration always syncs owner identity from MonthlyUser.
    vehicle.owner_name = monthly_user.full_name
    vehicle.phone = monthly_user.phone

    sub = models.Subscription(
        vehicle_id=sub_in.vehicle_id,
        monthly_user_id=sub_in.monthly_user_id,
        start_date=sub_in.start_date,
        end_date=sub_in.end_date,
        registered_at=get_vietnam_now(),
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@app.get("/api/subscriptions", response_model=List[schemas.Subscription])
def list_subscriptions(db: Session = Depends(get_db)):
    return db.query(models.Subscription).all()


@app.post("/api/monthly-registrations", response_model=schemas.MonthlyRegistrationResponse, status_code=status.HTTP_201_CREATED)
def create_monthly_registration(payload: schemas.MonthlyRegistrationCreate, db: Session = Depends(get_db)):
    plate_norm = ai_service.normalize_plate(payload.plate_number)
    if not ai_service.is_valid_vn_plate(plate_norm):
        raise HTTPException(status_code=400, detail="Bien so khong hop le")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date phai lon hon hoac bang start_date")

    monthly_user = None
    if payload.phone:
        monthly_user = (
            db.query(models.MonthlyUser)
            .filter(models.MonthlyUser.phone == payload.phone)
            .first()
        )

    if not monthly_user:
        monthly_user = models.MonthlyUser(
            full_name=payload.full_name,
            phone=payload.phone,
            address=payload.address,
        )
        db.add(monthly_user)
        db.flush()
    else:
        monthly_user.full_name = payload.full_name or monthly_user.full_name
        monthly_user.address = payload.address if payload.address is not None else monthly_user.address

    vehicle = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == plate_norm)
        .first()
    )
    if not vehicle:
        vehicle = models.Vehicle(
            plate_number=plate_norm,
            owner_name=monthly_user.full_name,
            phone=monthly_user.phone,
            note=payload.vehicle_note,
        )
        db.add(vehicle)
        db.flush()
    else:
        vehicle.owner_name = monthly_user.full_name
        vehicle.phone = monthly_user.phone
        if payload.vehicle_note is not None:
            vehicle.note = payload.vehicle_note

    now_date = get_vietnam_date()
    active_flag = payload.end_date >= now_date

    (
        db.query(models.Subscription)
        .filter(
            models.Subscription.vehicle_id == vehicle.id,
            models.Subscription.is_active == True,  # noqa: E712
        )
        .update({models.Subscription.is_active: False})
    )

    sub = models.Subscription(
        vehicle_id=vehicle.id,
        monthly_user_id=monthly_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        registered_at=get_vietnam_now(),
        is_active=active_flag,
    )
    db.add(sub)
    db.flush()

    rfid_card = None
    card_uid = (payload.rfid_card_uid or "").strip().upper().replace(" ", "").replace(":", "")
    if card_uid:
        existing_card = (
            db.query(models.RFIDCard)
            .filter(models.RFIDCard.card_uid == card_uid)
            .first()
        )
        if existing_card and existing_card.card_type != "monthly":
            raise HTTPException(status_code=400, detail="RFID nay dang la the guest")

        if existing_card:
            existing_card.card_type = "monthly"
            existing_card.monthly_user_id = monthly_user.id
            existing_card.vehicle_id = vehicle.id
            existing_card.expired_at = datetime.combine(payload.end_date, dt_time.max)
            existing_card.is_active = active_flag
            rfid_card = existing_card
        else:
            rfid_card = models.RFIDCard(
                card_uid=card_uid,
                card_type="monthly",
                monthly_user_id=monthly_user.id,
                vehicle_id=vehicle.id,
                expired_at=datetime.combine(payload.end_date, dt_time.max),
                is_active=active_flag,
            )
            db.add(rfid_card)

    db.commit()
    db.refresh(monthly_user)
    db.refresh(vehicle)
    db.refresh(sub)
    if rfid_card:
        db.refresh(rfid_card)

    return schemas.MonthlyRegistrationResponse(
        message="Dang ky ve thang thanh cong",
        subscription=sub,
        monthly_user=monthly_user,
        vehicle=vehicle,
        rfid_card=rfid_card,
    )


@app.get("/api/monthly-registrations", response_model=List[schemas.MonthlyRegistrationItem])
def list_monthly_registrations(db: Session = Depends(get_db)):
    subscriptions = (
        db.query(models.Subscription)
        .order_by(models.Subscription.registered_at.desc(), models.Subscription.id.desc())
        .all()
    )

    items: List[schemas.MonthlyRegistrationItem] = []
    for sub in subscriptions:
        user = sub.monthly_user
        vehicle = sub.vehicle
        if not user or not vehicle:
            continue

        card = (
            db.query(models.RFIDCard)
            .filter(
                models.RFIDCard.card_type == "monthly",
                models.RFIDCard.monthly_user_id == user.id,
                models.RFIDCard.vehicle_id == vehicle.id,
            )
            .order_by(models.RFIDCard.id.desc())
            .first()
        )

        items.append(
            schemas.MonthlyRegistrationItem(
                subscription_id=sub.id,
                monthly_user_id=user.id,
                monthly_user_name=user.full_name,
                monthly_user_phone=user.phone,
                vehicle_id=vehicle.id,
                plate_number=vehicle.plate_number,
                start_date=sub.start_date,
                end_date=sub.end_date,
                is_active=sub.is_active,
                rfid_card_id=card.id if card else None,
                rfid_card_uid=card.card_uid if card else None,
                registered_at=sub.registered_at,
            )
        )

    return items


@app.delete("/api/monthly-registrations/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monthly_registration(subscription_id: int, db: Session = Depends(get_db)):
    """
    Xóa một lượt đăng ký vé tháng.
    Tự động hoàn trả trạng thái của thẻ RFID tương ứng về 'available' và giải phóng thông tin liên kết.
    """
    sub = db.query(models.Subscription).get(subscription_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông tin đăng ký vé tháng")

    # Tìm thẻ RFID tương ứng được gán cho lượt đăng ký này
    card = (
        db.query(models.RFIDCard)
        .filter(
            models.RFIDCard.card_type == "monthly",
            models.RFIDCard.monthly_user_id == sub.monthly_user_id,
            models.RFIDCard.vehicle_id == sub.vehicle_id,
        )
        .first()
    )

    if card:
        # Giải phóng thẻ RFID trở lại dạng guest
        card.card_type = "guest"
        card.monthly_user_id = None
        card.vehicle_id = None
        card.expired_at = None
        card.is_active = True
        card.status = "available"

    # Giải phóng thông tin chủ xe trong bảng Vehicles
    if sub.vehicle:
        sub.vehicle.owner_name = None
        sub.vehicle.phone = None

    db.delete(sub)
    db.commit()
    return


# ============ MONTHLY USERS ============
@app.post("/api/monthly-users", response_model=schemas.MonthlyUser, status_code=status.HTTP_201_CREATED)
def create_monthly_user(payload: schemas.MonthlyUserCreate, db: Session = Depends(get_db)):
    monthly_user = models.MonthlyUser(
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
    )
    db.add(monthly_user)
    db.commit()
    db.refresh(monthly_user)
    return monthly_user


@app.get("/api/monthly-users", response_model=List[schemas.MonthlyUser])
def list_monthly_users(db: Session = Depends(get_db)):
    return db.query(models.MonthlyUser).order_by(models.MonthlyUser.id.desc()).all()


# ============ UTILS ============
# ============ RFID CARDS ============
@app.post("/api/rfid-cards", response_model=schemas.RFIDCard, status_code=status.HTTP_201_CREATED)
def create_rfid_card(payload: schemas.RFIDCardCreate, db: Session = Depends(get_db)):
    card_uid = (payload.card_uid or "").strip().upper().replace(" ", "").replace(":", "")
    card_type = (payload.card_type or "").strip().lower()
    if card_type not in ["monthly", "guest"]:
        raise HTTPException(status_code=400, detail="card_type must be monthly or guest")

    exists = db.query(models.RFIDCard).filter(models.RFIDCard.card_uid == card_uid).first()
    if exists:
        raise HTTPException(status_code=400, detail="The RFID da ton tai")

    if card_type == "monthly":
        if not payload.monthly_user_id or not payload.vehicle_id:
            raise HTTPException(status_code=400, detail="The monthly phai gan monthly_user_id va vehicle_id")
        monthly_user = db.query(models.MonthlyUser).get(payload.monthly_user_id)
        vehicle = db.query(models.Vehicle).get(payload.vehicle_id)
        if not monthly_user or not vehicle:
            raise HTTPException(status_code=404, detail="Khong tim thay user/xe de gan the monthly")

    card = models.RFIDCard(
        card_uid=card_uid,
        card_type=card_type,
        monthly_user_id=payload.monthly_user_id,
        vehicle_id=payload.vehicle_id,
        expired_at=payload.expired_at,
        is_active=True,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@app.get("/api/rfid-cards", response_model=List[schemas.RFIDCard])
def list_rfid_cards(db: Session = Depends(get_db)):
    return db.query(models.RFIDCard).order_by(models.RFIDCard.id.desc()).all()


# ============ PARKING CHECK-OUT (legacy) ============
@app.post("/api/parking/check-out", response_model=schemas.ParkingCheckoutResponse)
def parking_check_out(payload: schemas.ParkingCheckoutRequest, db: Session = Depends(get_db)):
    now = get_vietnam_now()

    session = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.plate_number == payload.plate_number,
            models.ParkingSession.time_out.is_(None),
        )
        .order_by(models.ParkingSession.time_in.desc())
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Khong tim thay phien gui dang mo cho bien so nay",
        )

    duration_minutes, fee = calculate_fee(now, session, db)
    session.time_out = now
    session.fee = fee
    session.gate_type = "exit"
    session.plate_out = payload.plate_number
    session.match_status = "matched"

    db.commit()
    db.refresh(session)

    return schemas.ParkingCheckoutResponse(
        session=session,
        duration_minutes=duration_minutes,
    )


# ============ FORCE CHECKOUT (Mất thẻ / Xe kẹt) ============
@app.post("/api/parking/force-checkout")
async def force_checkout(
    plate_number: str = Form(...),
    reason: str = Form("lost_card"),
    open_gate: bool = Form(True),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Bảo vệ tìm xe theo biển số, tính phí thủ công, kết thúc session.
    Tùy chọn mở cổng ra cho xe.
    """
    plate_norm = ai_service.normalize_plate(plate_number)
    now = get_vietnam_now()

    session = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.plate_number == plate_norm,
            models.ParkingSession.time_out.is_(None),
        )
        .order_by(models.ParkingSession.time_in.desc())
        .first()
    )
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy phiên gửi xe đang mở cho biển số {plate_norm}",
        )

    ticket_type = resolve_session_ticket_type(db, session)
    duration_minutes, fee = calculate_fee(now, session, db, ticket_type=ticket_type)

    session.time_out = now
    session.fee = fee
    session.plate_out = plate_norm
    session.match_status = "manual"

    # Cập nhật trạng thái thẻ RFID thành "available" khi force checkout
    if session.rfid_tag:
        rfid_card_to_release = get_rfid_card(db, session.rfid_tag)
        if rfid_card_to_release:
            rfid_card_to_release.status = "available"

    db.commit()
    db.refresh(session)

    # Mở cổng ra nếu cần
    gate_opened = False
    if open_gate:
        global esp32_ip
        if esp32_ip:
            import urllib.request
            import urllib.error
            from fastapi.concurrency import run_in_threadpool

            def send_open():
                try:
                    req = urllib.request.Request(
                        f"http://{esp32_ip}/open-gate?gate=out", method="GET"
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        return resp.getcode() == 200
                except Exception:
                    return False

            gate_opened = await run_in_threadpool(send_open)

    await notify_clients("parking_update", {
        "action": "force_checkout",
        "gate_type": "exit",
        "plate": plate_norm,
        "fee": fee,
        "reason": reason,
        "session_id": session.id,
    })

    fee_fmt = f"{int(fee):,}đ" if fee > 0 else "Miễn phí (vé tháng)"
    return {
        "status": "ok",
        "session_id": session.id,
        "plate_number": plate_norm,
        "duration_minutes": duration_minutes,
        "fee": fee,
        "fee_display": fee_fmt,
        "gate_opened": gate_opened,
        "message": f"Đã checkout thủ công xe {plate_norm}. Phí: {fee_fmt}. Thời gian gửi: {duration_minutes} phút.",
    }


# ============ FIRE RESET (Tắt báo động cháy từ xa) ============
@app.post("/api/fire/reset")
async def reset_fire_alarm(api_key: str = Depends(verify_api_key)):
    """
    Gọi ESP32 để tắt chế độ báo động cháy (Ưu tiên MQTT, dự phòng HTTP).
    Chỉ bảo vệ mới được phép gọi sau khi xác nhận an toàn.
    """
    # 1. Gửi lệnh qua MQTT
    if mqtt_manager.is_connected:
        db = SessionLocal()
        try:
            resolved_count = resolve_open_fire_alerts(db)
        finally:
            db.close()
        mqtt_manager.publish_reset_fire("esp32-barrier-01")
        await notify_clients("fire_reset", {
            "message": "Đã tắt báo động cháy qua MQTT. Hệ thống trở lại trạng thái bình thường.",
            "resolved_count": resolved_count,
            "fire_active": False,
        })
        return {"status": "ok", "message": "Đã gửi lệnh tắt báo động cháy thành công qua MQTT.", "resolved_count": resolved_count}

    # 2. Gửi lệnh qua HTTP
    global esp32_ip
    if not esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 offline (cả MQTT và HTTP Web Server đều không khả dụng).",
        )

    import urllib.request
    import urllib.error
    from fastapi.concurrency import run_in_threadpool

    def send_reset():
        try:
            req = urllib.request.Request(
                f"http://{esp32_ip}/reset-fire", method="GET"
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            return -1, str(e.reason)
        except Exception as e:
            return -1, str(e)

    code, body = await run_in_threadpool(send_reset)

    if code == 200:
        db = SessionLocal()
        try:
            resolved_count = resolve_open_fire_alerts(db)
        finally:
            db.close()
        await notify_clients("fire_reset", {
            "message": "Đã tắt báo động cháy qua HTTP. Hệ thống trở lại trạng thái bình thường.",
            "resolved_count": resolved_count,
            "fire_active": False,
        })
        return {"status": "ok", "message": "Đã gửi lệnh tắt báo động cháy thành công qua HTTP.", "resolved_count": resolved_count}
    else:
        raise HTTPException(
            status_code=502,
            detail=f"Không thể kết nối ESP32 để reset fire alarm: {body}",
        )

@app.get("/api/parking-history", response_model=List[schemas.ParkingHistoryItem])
def list_parking_history(limit: int = 100, db: Session = Depends(get_db)):
    sessions = (
        db.query(models.ParkingSession)
        .order_by(models.ParkingSession.time_in.desc(), models.ParkingSession.id.desc())
        .limit(limit)
        .all()
    )

    items: List[schemas.ParkingHistoryItem] = []
    for session in sessions:
        duration_minutes = None
        if session.time_out:
            duration_minutes = int((session.time_out - session.time_in).total_seconds() // 60)

        items.append(
            schemas.ParkingHistoryItem(
                session_id=session.id,
                plate_number=session.plate_number,
                ticket_type=resolve_session_ticket_type(db, session),
                gate_type=session.gate_type,
                trigger_type=session.trigger_type,
                time_in=session.time_in,
                time_out=session.time_out,
                duration_minutes=duration_minutes,
                fee=session.fee or 0,
                match_status=session.match_status,
            )
        )
    return items


@app.get("/api/parking/export")
def export_parking_history(db: Session = Depends(get_db)):
    import csv
    import io
    
    sessions = (
        db.query(models.ParkingSession)
        .order_by(models.ParkingSession.time_in.desc(), models.ParkingSession.id.desc())
        .all()
    )

    def generate():
        # Trả về UTF-8 BOM để Excel hiển thị đúng tiếng Việt
        yield "\ufeff".encode('utf-8')
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Tiêu đề cột
        writer.writerow([
            "Mã phiên", "Biển số xe", "Loại vé", "Cổng", 
            "Cách thức", "Thời gian vào", "Thời gian ra", 
            "Thời gian đỗ (phút)", "Phí gửi (VND)", "Trạng thái"
        ])
        yield output.getvalue().encode('utf-8')
        output.seek(0)
        output.truncate(0)

        for session in sessions:
            duration = ""
            if session.time_out:
                duration = str(int((session.time_out - session.time_in).total_seconds() // 60))
            
            time_in_str = session.time_in.strftime("%Y-%m-%d %H:%M:%S") if session.time_in else ""
            time_out_str = session.time_out.strftime("%Y-%m-%d %H:%M:%S") if session.time_out else ""
            ticket_type = resolve_session_ticket_type(db, session)
            
            # Map values to Vietnamese for friendly CSV report
            gate = "Cổng vào" if session.gate_type == "entry" else "Cổng ra"
            trigger = "Tự động" if session.trigger_type == "sensor" else ("Thẻ RFID" if session.trigger_type == "rfid" else "Thủ công")
            match_status_vn = "Hợp lệ" if session.match_status == "matched" else (
                "Fuzzy (Nhận diện mờ)" if session.match_status == "fuzzy_matched" else (
                    "Đang chờ" if session.match_status == "pending" else (
                        "Từ chối/Bị hủy" if session.match_status == "ignored" else session.match_status or ""
                    )
                )
            )

            writer.writerow([
                session.id,
                session.plate_number,
                "Vé tháng" if ticket_type == "monthly" else "Vé lượt",
                gate,
                trigger,
                time_in_str,
                time_out_str,
                duration,
                int(session.fee or 0),
                match_status_vn
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)

    headers = {
        'Content-Disposition': 'attachment; filename="parking_history.csv"',
        'Content-Type': 'text/csv; charset=utf-8',
    }
    return StreamingResponse(generate(), headers=headers)


# ============ FIRE ALERTS ============
def set_fire_alarm_active(db: Session, active: bool) -> None:
    set_config_text(db, "fire_alarm_active", "1" if active else "0")


def get_fire_alarm_active(db: Session) -> bool:
    return get_config_bool(db, "fire_alarm_active", False)


def resolve_open_fire_alerts(db: Session) -> int:
    count = (
        db.query(models.FireAlert)
        .filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
        .update({models.FireAlert.is_acknowledged: True}, synchronize_session=False)
    )
    set_fire_alarm_active(db, False)
    db.commit()
    return int(count or 0)


def handle_critical_fire_gate_open() -> bool:
    global _last_fire_gate_open_at
    now = time_module.time()
    if now - _last_fire_gate_open_at < FIRE_GATE_OPEN_COOLDOWN_SECONDS:
        return False
    if not mqtt_manager.is_connected:
        logger.warning("Fire critical gate open skipped because MQTT is disconnected")
        return False
    mqtt_manager.publish_open_gate("esp32-barrier-01", "in")
    mqtt_manager.publish_open_gate("esp32-barrier-01", "out")
    _last_fire_gate_open_at = now
    return True


@app.post("/api/fire-alerts", response_model=schemas.FireAlert)
async def create_fire_alert(payload: schemas.FireAlertCreate, db: Session = Depends(get_db)):
    alert = models.FireAlert(
        sensor_id=payload.sensor_id,
        level=payload.level,
        message=payload.message,
    )
    db.add(alert)
    if payload.level == "critical":
        set_fire_alarm_active(db, True)
    db.commit()
    db.refresh(alert)

    gate_opened = handle_critical_fire_gate_open() if payload.level == "critical" else False
    
    # Thông báo hỏa hoạn qua WebSocket ngay lập tức
    await notify_clients("fire_alert", {
        "id": alert.id,
        "sensor_id": alert.sensor_id,
        "message": alert.message,
        "level": alert.level,
        "gate_opened": gate_opened,
    })
    
    return alert


@app.get("/api/fire-alerts", response_model=List[schemas.FireAlert])
def list_fire_alerts(
    unacked_only: bool = False,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(models.FireAlert)
    if unacked_only:
        query = query.filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
    return query.order_by(models.FireAlert.created_at.desc()).limit(limit).all()


@app.get("/api/fire/status", response_model=schemas.FireStatus)
def get_fire_status(db: Session = Depends(get_db)):
    unacknowledged_count = (
        db.query(models.FireAlert)
        .filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
        .count()
    )
    critical_count = (
        db.query(models.FireAlert)
        .filter(
            models.FireAlert.is_acknowledged == False,  # noqa: E712
            models.FireAlert.level == "critical",
        )
        .count()
    )
    active = get_fire_alarm_active(db) or critical_count > 0
    message = (
        "ĐANG BÁO CHÁY - Cổng vào/ra đang được giữ mở cho đến khi bảo vệ reset."
        if active
        else "Hệ thống báo cháy đang bình thường."
    )
    return schemas.FireStatus(
        active=active,
        unacknowledged_count=unacknowledged_count,
        critical_count=critical_count,
        message=message,
    )


@app.patch("/api/fire-alerts/{alert_id}/ack", response_model=schemas.FireAlert)
def ack_fire_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(models.FireAlert).get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Khong tim thay canh bao")
    alert.is_acknowledged = True
    db.commit()
    db.refresh(alert)
    return alert


# ============ DASHBOARD ============
@app.get("/api/dashboard", response_model=schemas.DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    today = get_vietnam_date()
    start_of_day = datetime(today.year, today.month, today.day)

    total_in_bay = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_(None),
            models.ParkingSession.match_status != "ignored"
        )
        .count()
    )

    today_total_in = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_in >= start_of_day,
            models.ParkingSession.match_status != "ignored"
        )
        .count()
    )

    today_total_out = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
            models.ParkingSession.match_status != "ignored"
        )
        .count()
    )

    today_revenue = (
        db.query(models.ParkingSession.fee)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
            models.ParkingSession.match_status != "ignored"
        )
    )
    total_fee = sum(row[0] or 0 for row in today_revenue)

    max_slots = int(get_system_config_value(db, "max_parking_slots", 50))
    max_guest_slots = int(get_system_config_value(db, "max_guest_slots", max_slots))
    max_monthly_slots = int(get_system_config_value(db, "max_monthly_slots", max_slots))
    near_full_threshold = get_system_config_value(db, "parking_near_full_threshold", 0.7)
    almost_full_threshold = get_system_config_value(db, "parking_almost_full_threshold", 0.9)
    guest_in_bay, monthly_in_bay = count_open_sessions_by_ticket_type(db)
    capacity = build_capacity_status(
        total_in_bay,
        max_slots,
        near_full_threshold=near_full_threshold,
        almost_full_threshold=almost_full_threshold,
    )
    guest_capacity = build_capacity_status(
        guest_in_bay,
        max_guest_slots,
        near_full_threshold=near_full_threshold,
        almost_full_threshold=almost_full_threshold,
    )
    monthly_capacity = build_capacity_status(
        monthly_in_bay,
        max_monthly_slots,
        near_full_threshold=near_full_threshold,
        almost_full_threshold=almost_full_threshold,
    )

    return schemas.DashboardStats(
        total_in_bay=total_in_bay,
        guest_in_bay=guest_in_bay,
        monthly_in_bay=monthly_in_bay,
        today_total_in=today_total_in,
        today_total_out=today_total_out,
        today_revenue=total_fee,
        max_slots=capacity["max_slots"],
        available_slots=capacity["available_slots"],
        occupancy_percent=capacity["occupancy_percent"],
        capacity_status=capacity["capacity_status"],
        capacity_message=capacity["capacity_message"],
        near_full_threshold=capacity["near_full_threshold"],
        almost_full_threshold=capacity["almost_full_threshold"],
        max_guest_slots=guest_capacity["max_slots"],
        available_guest_slots=guest_capacity["available_slots"],
        guest_capacity_status=guest_capacity["capacity_status"],
        guest_capacity_message=guest_capacity["capacity_message"],
        max_monthly_slots=monthly_capacity["max_slots"],
        available_monthly_slots=monthly_capacity["available_slots"],
        monthly_capacity_status=monthly_capacity["capacity_status"],
        monthly_capacity_message=monthly_capacity["capacity_message"],
    )

