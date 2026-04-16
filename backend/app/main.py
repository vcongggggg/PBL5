from datetime import datetime
import json
import os
import uuid
from typing import List, Optional, Tuple

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import ai_service, models, schemas
from .database import Base, engine, get_db

Base.metadata.create_all(bind=engine)


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


sync_schema()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PBL5 Smart Parking API")

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

    filename = f"capture_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as file_obj:
        file_obj.write(image_bytes)

    return file_path


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

    today = datetime.utcnow().date()
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


def calculate_fee(now: datetime, session: models.ParkingSession, db: Session) -> Tuple[int, float]:
    price_per_hour = get_system_config_value(db, "price_per_hour", 5000.0)

    duration_seconds = (now - session.time_in).total_seconds()
    duration_hours = max(duration_seconds / 3600.0, 0.0)

    hours_rounded = int(duration_hours) if duration_hours.is_integer() else int(duration_hours) + 1
    if hours_rounded == 0:
        hours_rounded = 1

    fee = hours_rounded * price_per_hour
    duration_minutes = int(duration_seconds // 60)
    return duration_minutes, fee


def log_sensor_event(
    db: Session,
    gate_type: str,
    trigger_type: str,
    source_id: Optional[str],
    rfid_tag: Optional[str],
    payload: Optional[dict] = None,
) -> None:
    event = models.SensorEventLog(
        event_type=trigger_type,
        gate_type=gate_type,
        source_id=source_id,
        rfid_tag=rfid_tag,
        payload=json.dumps(payload) if payload else None,
    )
    db.add(event)
    db.commit()


def get_rfid_card(db: Session, rfid_tag: Optional[str]) -> Optional[models.RFIDCard]:
    if not rfid_tag:
        return None
    return (
        db.query(models.RFIDCard)
        .filter(models.RFIDCard.card_uid == rfid_tag.strip())
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
    if card.expired_at and card.expired_at < datetime.utcnow():
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

        today = datetime.utcnow().date()
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


def process_gate_scan(
    db: Session,
    image_bytes: bytes,
    filename: Optional[str],
    gate_type: str,
    trigger_type: str,
    source_id: Optional[str],
    rfid_tag: Optional[str],
) -> schemas.GateScanResponse:
    gate_type = (gate_type or "entry").lower()
    trigger_type = (trigger_type or "sensor").lower()

    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    if trigger_type not in ["sensor", "rfid", "manual"]:
        raise HTTPException(status_code=400, detail="trigger_type must be sensor, rfid or manual")

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

    image_path = save_upload_image(image_bytes, filename)
    now = datetime.utcnow()

    log_sensor_event(
        db=db,
        gate_type=gate_type,
        trigger_type=trigger_type,
        source_id=source_id,
        rfid_tag=rfid_tag,
        payload={
            "plate": recognized_plate,
            "confidence": confidence,
            "valid_plate": valid_plate,
            "rfid_card_type": rfid_card_type,
        },
    )

    if gate_type == "entry":
        vehicle_type, vehicle_msg = resolve_vehicle_type(db, recognized_plate)
        can_open = valid_plate and confidence >= threshold
        action = "open" if can_open else "ignore"

        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == recognized_plate)
            .first()
        )

        session = models.ParkingSession(
            vehicle_id=vehicle.id if vehicle else None,
            plate_number=recognized_plate or "UNKNOWN",
            direction="in",
            time_in=now,
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
        db.commit()
        db.refresh(session)

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
            message=vehicle_msg if can_open else "Khong du dieu kien mo cong",
        )

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
            message="Bien so ra khong hop le hoac confidence thap",
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
            message="Khong tim thay du lieu bien vao trong DB",
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
            message="The RFID khong khop voi phien gui trong bai",
        )

    duration_minutes, fee = calculate_fee(now, open_session, db)
    open_session.time_out = now
    open_session.direction = "out"
    open_session.fee = fee
    open_session.gate_type = "exit"
    open_session.trigger_type = trigger_type
    open_session.trigger_source_id = source_id
    open_session.rfid_tag = rfid_tag
    open_session.rfid_card_id = rfid_card.id if rfid_card else open_session.rfid_card_id
    open_session.rfid_card_type = rfid_card_type or open_session.rfid_card_type
    open_session.plate_out = recognized_plate
    open_session.confidence_out = confidence
    open_session.match_status = "matched"

    db.commit()
    db.refresh(open_session)

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
        direction=direction,
        time_in=datetime.utcnow(),
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
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


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
        if card.expired_at and card.expired_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="The RFID da het han")
        rfid_card_type = card.card_type

    log_sensor_event(
        db=db,
        gate_type=gate_type,
        trigger_type=trigger_type,
        source_id=payload.source_id,
        rfid_tag=payload.rfid_tag,
        payload={"mode": "manual-trigger", "rfid_card_type": rfid_card_type},
    )

    return schemas.GateTriggerResponse(
        status="ok",
        gate_type=gate_type,
        trigger_type=trigger_type,
        source_id=payload.source_id,
        rfid_tag=payload.rfid_tag,
        rfid_card_type=rfid_card_type,
        message="Da nhan trigger, frontend co the bat dau mo camera de quet",
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

    return process_gate_scan(
        db=db,
        image_bytes=image_bytes,
        filename=file.filename,
        gate_type=gate_type,
        trigger_type=trigger_type,
        source_id=source_id,
        rfid_tag=rfid_tag,
    )


# ============ ESP32 ENDPOINTS ============
@app.post("/api/esp/events", response_model=schemas.EspEventResponse)
def handle_esp_event(payload: schemas.EspEventRequest, db: Session = Depends(get_db)):
    detected_plate, confidence = ai_service.recognize_plate_demo()
    result = process_checkin_compat(
        db=db,
        plate=detected_plate,
        confidence=confidence,
        direction=payload.direction,
        image_path=None,
    )

    return schemas.EspEventResponse(
        action=result.action,
        plate=result.plate,
        vehicle_type=result.vehicle_type,
        message=result.message,
    )


@app.post("/api/esp/manual-open")
def handle_manual_open(payload: schemas.ManualOpenRequest):
    return {
        "status": "ok",
        "device_id": payload.device_id,
        "reason": payload.reason,
        "time": datetime.utcnow().isoformat(),
    }


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

    vehicle = models.Vehicle(
        plate_number=plate_norm,
        owner_name=vehicle_in.owner_name,
        phone=vehicle_in.phone,
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

    sub = models.Subscription(
        vehicle_id=sub_in.vehicle_id,
        monthly_user_id=sub_in.monthly_user_id,
        start_date=sub_in.start_date,
        end_date=sub_in.end_date,
        registered_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@app.get("/api/subscriptions", response_model=List[schemas.Subscription])
def list_subscriptions(db: Session = Depends(get_db)):
    return db.query(models.Subscription).all()


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


# ============ RFID CARDS ============
@app.post("/api/rfid-cards", response_model=schemas.RFIDCard, status_code=status.HTTP_201_CREATED)
def create_rfid_card(payload: schemas.RFIDCardCreate, db: Session = Depends(get_db)):
    card_uid = (payload.card_uid or "").strip()
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
    now = datetime.utcnow()

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
    session.direction = "out"
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


# ============ FIRE ALERTS ============
@app.post("/api/fire-alerts", response_model=schemas.FireAlert)
def create_fire_alert(payload: schemas.FireAlertCreate, db: Session = Depends(get_db)):
    alert = models.FireAlert(
        sensor_id=payload.sensor_id,
        level=payload.level,
        message=payload.message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
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
    today = datetime.utcnow().date()
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

    return schemas.DashboardStats(
        total_in_bay=total_in_bay,
        today_total_in=today_total_in,
        today_total_out=today_total_out,
        today_revenue=total_fee,
    )
