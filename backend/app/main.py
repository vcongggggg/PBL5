from datetime import datetime, time as dt_time, timezone, timedelta
import os
import time as time_module
import threading
import uuid
from typing import List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
import json

from fastapi.responses import StreamingResponse
from . import ai_service, models, schemas, camera_service
from .camera_service import camera_manager
from .database import Base, engine, get_db

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


sync_schema()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PBL5 Smart Parking API")

# ============ WEBSOCKET MANAGER ============
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

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

@app.on_event("shutdown")
def shutdown_event():
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


def save_upload_image(image_bytes: bytes, original_name: Optional[str]) -> Optional[str]:
    if not image_bytes:
        return None

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    upload_dir = os.path.join(base_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(original_name or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
        ext = ".jpg"

    filename = f"capture_{get_vietnam_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as file_obj:
        file_obj.write(image_bytes)

    return file_path


def get_config_text(db: Session, key: str, default: str = "") -> str:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config or not config.value:
        return default
    return str(config.value)


def resolve_vehicle_type(db: Session, plate_norm: str) -> Tuple[str, str]:
    if not plate_norm or not ai_service.is_valid_vn_plate(plate_norm):
        return "unknown", "Bien so khong hop le"

    vehicle = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == plate_norm)
        .first()
    )
    if not vehicle:
        return "guest", "Xe khong co trong danh sach"

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
        return "monthly", "Xe ve thang, con han"
    return "guest", "Xe ve thang, HET han"


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
) -> Tuple[Optional[models.RFIDCard], Optional[str]]:
    if trigger_type != "rfid":
        return None, None

    if not rfid_tag:
        return None, "RFID trigger can thiet lap rfid_tag"

    card = get_rfid_card(db, rfid_tag)
    if not card:
        return None, "Khong tim thay the RFID"
    if not card.is_active:
        return None, "The RFID da bi khoa"
    if card.expired_at and card.expired_at < get_vietnam_now():
        return None, "The RFID da het han"
    if card.card_type not in ["monthly", "guest"]:
        return None, "Loai the RFID khong hop le"

    if card.card_type == "monthly":
        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == recognized_plate)
            .first()
        )
        if not vehicle:
            return None, "The thang chi ap dung cho xe da dang ky"
        if card.vehicle_id and card.vehicle_id != vehicle.id:
            return None, "The RFID khong dung voi xe dang quet"

        today = get_vietnam_date()
        active_sub = (
            db.query(models.Subscription)
            .filter(
                models.Subscription.vehicle_id == vehicle.id,
                models.Subscription.is_active == True,  # noqa: E712
                models.Subscription.start_date <= today,
                models.Subscription.end_date >= today,
            )
            .order_by(models.Subscription.id.desc())
            .first()
        )
        if not active_sub:
            return None, "Khong tim thay dang ky ve thang con han"
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
    rfid_card, rfid_error = validate_rfid_for_scan(db, trigger_type, rfid_tag, recognized_plate)
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
            max_slots = int(get_system_config_value(db, "max_parking_slots", 50))
            active_vehicles_count = (
                db.query(models.ParkingSession)
                .filter(models.ParkingSession.time_out.is_(None))
                .count()
            )
            if active_vehicles_count >= max_slots:
                # Nếu không phải manual trigger thì chặn mở barrier
                if trigger_type != "manual":
                    action = "ignore"
                    can_open = False
                    vehicle_msg = f"Bãi xe đã đầy chỗ ({active_vehicles_count}/{max_slots} xe)!"

        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == recognized_plate)
            .first()
        )

        session = models.ParkingSession(
            vehicle_id=vehicle.id if vehicle else None,
            plate_number=recognized_plate or "UNKNOWN",
            time_in=now,
            time_out=None if action == "open" else now,
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
            match_status="pending" if action == "open" else "ignored",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # Thông báo qua WebSocket
        await notify_clients("parking_update", {
            "action": action,
            "gate_type": "entry",
            "plate": recognized_plate,
            "session_id": session.id
        })

        return schemas.GateScanResponse(
            action=action,
            gate_type="entry",
            trigger_type=trigger_type,
            rfid_card_type=rfid_card_type,
            plate_in=session.plate_in,
            recognized_plate=recognized_plate or "UNKNOWN",
            confidence=confidence,
            valid_plate=valid_plate,
            matched=True,
            session_id=session.id,
            message=vehicle_msg if can_open else (vehicle_msg if not has_rfid else "Không đủ điều kiện mở cổng"),
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

    if not valid_plate or confidence < threshold:
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            plate_out=recognized_plate or "UNKNOWN",
            recognized_plate=recognized_plate or "UNKNOWN",
            confidence=confidence,
            valid_plate=valid_plate,
            matched=False,
            message="Biển số ra không hợp lệ hoặc ảnh mờ",
        )

    if not open_session:
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
            message="Không tìm thấy thông tin xe vào (Thẻ này chưa được dùng)",
        )

    # So sánh Biển số ra với Biển số lúc vào - Fuzzy matching cho phép sai lệch 1 ký tự (OCR mờ)
    plate_distance = levenshtein_distance(
        ai_service.normalize_plate(open_session.plate_number),
        recognized_plate
    )
    MAX_PLATE_DISTANCE = 1  # Cho phép tối đa sai 1 ký tự
    if plate_distance > MAX_PLATE_DISTANCE:
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
            message=f"Biển số ra ({recognized_plate}) KHÔNG KHỚP với biển lúc vào ({open_session.plate_number})! (sai {plate_distance} ký tự)",
        )

    if trigger_type == "rfid" and open_session.rfid_card_id and rfid_card and open_session.rfid_card_id != rfid_card.id:
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
            message="Thẻ RFID này không khớp với thẻ lúc vào của xe này",
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
    open_session.match_status = "matched" if plate_distance == 0 else "fuzzy_matched"

    db.commit()
    db.refresh(open_session)

    # Thông báo qua WebSocket
    await notify_clients("parking_update", {
        "action": "open",
        "gate_type": "exit",
        "plate": recognized_plate,
        "fee": fee,
        "session_id": open_session.id
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
        message="Bien so ra trung khop bien vao, cho phep xe ra",
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
    db.add(session)
    db.commit()
    db.refresh(session)

    return schemas.ParkingCheckinResponse(
        action="open" if valid_plate and confidence >= threshold else "ignore",
        plate=plate_norm or "UNKNOWN",
        confidence=confidence,
        valid_plate=valid_plate,
        vehicle_type=vehicle_type,
        message=message,
        session_id=session.id,
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
    index = camera_service.CAMERA_IN_INDEX if gate_type == "entry" else camera_service.CAMERA_OUT_INDEX
    image_bytes = camera_service.capture_image(index)
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


# ============ ESP32 ENDPOINTS ============
# Cooldown: tránh xử lý event trùng lặp từ cảm biến IR
_esp_event_cooldown = {}  # {"in": timestamp, "out": timestamp}
ESP_EVENT_COOLDOWN_SECONDS = 5  # Bỏ qua event cùng hướng trong 5 giây

@app.post("/api/esp/events", response_model=schemas.EspEventResponse)
async def handle_esp_event(
    payload: schemas.EspEventRequest,
    request: Request,
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
    
    # 1. Xac dinh camera can chup
    cam_index = camera_service.CAMERA_IN_INDEX if direction == "in" else camera_service.CAMERA_OUT_INDEX
    
    # 2. Chụp ảnh từ Webcam
    image_bytes = camera_service.capture_image(cam_index)
    
    override_plate = None
    override_confidence = None
    if not image_bytes:
        # Fallback neu camera loi / khong co camera: su dung mock plate de test luong db
        detected_plate, confidence = ai_service.recognize_plate_demo()
        override_plate = detected_plate
        override_confidence = confidence
        
        # Tao anh gia lap
        import numpy as np
        import cv2
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.putText(dummy_img, "MOCK", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        _, buffer = cv2.imencode('.jpg', dummy_img)
        image_bytes = buffer.tobytes()
    
    if override_plate is not None:
        plate_raw, confidence = override_plate, (override_confidence or 0.9)
    else:
        plate_raw, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    
    recognized_plate = ai_service.normalize_plate(plate_raw)
    
    # Save the image first to get image_path
    image_path = save_upload_image(image_bytes, f"esp_event_{direction}.jpg")

    # 3. Đưa thông tin vào hàng đợi tạm chờ quẹt thẻ (Database persistent)
    db.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).delete()
    
    pending = models.PendingScan(
        gate_type=gate_type,
        plate_number=recognized_plate,
        confidence=confidence,
        image_path=image_path,
        device_id=payload.device_id
    )
    db.add(pending)
    db.commit()
    
    # 4. Gửi WebSocket báo cho Frontend cập nhật UI
    await notify_clients("pending_scan", {
        "gate_type": gate_type,
        "recognized_plate": recognized_plate,
        "confidence": confidence,
        "message": "Chờ quẹt thẻ RFID..."
    })
    
    vehicle_type, _ = resolve_vehicle_type(db, recognized_plate)
    
    return schemas.EspEventResponse(
        action="ignore",
        plate=recognized_plate,
        vehicle_type=vehicle_type,
        message=f"Đã nhận diện biển số {recognized_plate}. Vui lòng quẹt thẻ RFID.",
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
async def force_open_gate(gate_type: str = Form(...), api_key: str = Depends(verify_api_key)):
    """
    API gửi lệnh mở cổng thủ công từ Web UI tới ESP32 WebServer.
    """
    global esp32_ip
    if not esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 chưa kết nối hoặc chưa cập nhật IP lên Backend."
        )

    gate = "in" if gate_type == "entry" else "out"
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
        await notify_clients("parking_update", {
            "action": "open_manual",
            "gate_type": gate_type,
            "message": f"Mở cổng {gate_type} thủ công từ xa thành công"
        })
        return {"status": "ok", "message": f"Đã gửi lệnh mở cổng {gate_type} thành công."}
    else:
        raise HTTPException(
            status_code=502,
            detail=f"Không thể kết nối hoặc lỗi phản hồi từ ESP32: {body}"
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
    direction = payload.direction or "in"
    gate_type = "entry" if direction == "in" else "exit"
    
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

    # 2. Kiểm tra xem có biển số xe đang chờ trong hàng đợi không
    pending = (
        db.query(models.PendingScan)
        .filter(models.PendingScan.gate_type == gate_type)
        .first()
    )
    EXPIRE_SECONDS = 45  # Tăng thời hạn hàng đợi lên 45 giây để thoải mái thao tác
    
    now_dt = get_vietnam_now()
    if not pending or (now_dt - pending.created_at).total_seconds() > EXPIRE_SECONDS:
        return schemas.EspRfidResponse(
            action="ignore",
            uid=uid_norm,
            message="Vui lòng đỗ xe đúng vị trí cảm biến trước khi quẹt thẻ",
            direction=direction,
            gate_id=payload.gate_id,
        )

    # 3. Lấy thông tin biển số và ảnh chụp từ DB
    recognized_plate = pending.plate_number
    image_path = pending.image_path
    confidence = pending.confidence

    # 4. Goi process_gate_scan de thuc hien logic nghiep vu
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

    # 5. Nếu mở cổng thành công, xóa biển số khỏi hàng đợi tạm
    if result.action == "open":
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
    db.commit()
    db.refresh(alert)

    # Broadcast cảnh báo lên WebSocket
    await notify_clients("fire_alert", {
        "id": alert.id,
        "sensor_id": alert.sensor_id,
        "message": alert.message,
        "level": alert.level,
        "from_esp32": True,
    })

    return schemas.FireAlertResponse(
        status="ok",
        action="open_all",
        message=payload.message or f"Fire alert from {payload.device_id}",
    )


# ============ CAMERA STREAMING ============

def gen_frames(camera_index: int):
    while camera_manager.is_running:
        frame_bytes = camera_manager.capture(camera_index)
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        else:
            time_module.sleep(0.5)
        time_module.sleep(0.04)  # ~25 FPS

@app.get("/api/camera/stream/{gate_type}")
def video_feed(gate_type: str):
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="Invalid gate type")
    index = camera_service.CAMERA_IN_INDEX if gate_type == "entry" else camera_service.CAMERA_OUT_INDEX
    return StreamingResponse(gen_frames(index),
                             media_type="multipart/x-mixed-replace; boundary=frame")


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
    scan_result = process_gate_scan(
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
        registered_at=datetime.utcnow(),
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
    session.match_status = "force_checkout"
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
    Gọi ESP32 để tắt chế độ báo động cháy.
    Chỉ bảo vệ mới được phép gọi sau khi xác nhận an toàn.
    """
    global esp32_ip
    if not esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 chưa kết nối hoặc chưa cập nhật IP lên Backend.",
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
        await notify_clients("fire_reset", {
            "message": "Đã tắt báo động cháy. Hệ thống trở lại trạng thái bình thường.",
        })
        return {"status": "ok", "message": "Đã gửi lệnh tắt báo động cháy thành công."}
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
@app.post("/api/fire-alerts", response_model=schemas.FireAlert)
async def create_fire_alert(payload: schemas.FireAlertCreate, db: Session = Depends(get_db)):
    alert = models.FireAlert(
        sensor_id=payload.sensor_id,
        level=payload.level,
        message=payload.message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    
    # Thông báo hỏa hoạn qua WebSocket ngay lập tức
    await notify_clients("fire_alert", {
        "id": alert.id,
        "sensor_id": alert.sensor_id,
        "message": alert.message,
        "level": alert.level
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
        .filter(models.ParkingSession.time_out.is_(None))
        .count()
    )

    today_total_in = (
        db.query(models.ParkingSession)
        .filter(models.ParkingSession.time_in >= start_of_day)
        .count()
    )

    today_total_out = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
        )
        .count()
    )

    today_revenue = (
        db.query(models.ParkingSession.fee)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
        )
    )
    total_fee = sum(row[0] or 0 for row in today_revenue)

    max_slots = int(get_system_config_value(db, "max_parking_slots", 50))
    available_slots = max(0, max_slots - total_in_bay)

    return schemas.DashboardStats(
        total_in_bay=total_in_bay,
        today_total_in=today_total_in,
        today_total_out=today_total_out,
        today_revenue=total_fee,
        max_slots=max_slots,
        available_slots=available_slots,
    )

