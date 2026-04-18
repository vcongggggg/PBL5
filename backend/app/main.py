from datetime import datetime
import os
import uuid
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import ai_service, models, schemas
from .database import Base, engine, get_db

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

    filename = f"checkin_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, filename)
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    return file_path


def get_config_text(db: Session, key: str, default: str = "") -> str:
    config = db.query(models.SystemConfig).filter(models.SystemConfig.key == key).first()
    if not config or not config.value:
        return default
    return str(config.value)


def process_checkin(
    db: Session,
    plate: str,
    confidence: float,
    direction: str,
    image_path: Optional[str] = None,
) -> schemas.ParkingCheckinResponse:
    now = datetime.utcnow()
    plate_norm = ai_service.normalize_plate(plate)
    valid_plate = ai_service.is_valid_vn_plate(plate_norm)

    threshold = get_system_config_value(db, "plate_confidence_threshold", 0.6)
    action = "open" if (valid_plate and confidence >= threshold) else "ignore"

    vehicle = None
    if plate_norm:
        vehicle = (
            db.query(models.Vehicle)
            .filter(models.Vehicle.plate_number == plate_norm)
            .first()
        )

    vehicle_type = "unknown"
    message = "Bien so khong hop le"

    if valid_plate:
        if vehicle:
            active_sub = (
                db.query(models.Subscription)
                .filter(
                    models.Subscription.vehicle_id == vehicle.id,
                    models.Subscription.is_active == True,  # noqa: E712
                    models.Subscription.start_date <= now.date(),
                    models.Subscription.end_date >= now.date(),
                )
                .first()
            )
            if active_sub:
                vehicle_type = "monthly"
                message = "Xe ve thang, con han"
            else:
                vehicle_type = "guest"
                message = "Xe ve thang, HET han"
        else:
            vehicle_type = "guest"
            message = "Xe khong co trong danh sach"

    session = models.ParkingSession(
        vehicle_id=vehicle.id if vehicle else None,
        plate_number=plate_norm or "UNKNOWN",
        direction=direction,
        time_in=now,
        fee=0,
        image_path=image_path,
    )
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
        session_id=session.id,
    )


@app.get("/health")
def health_check():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ============ ESP32 ENDPOINTS ============
@app.post("/api/esp/events", response_model=schemas.EspEventResponse)
def handle_esp_event(
    payload: schemas.EspEventRequest, db: Session = Depends(get_db)
):
    """
    Endpoint ESP32: nhan su kien xe va xu ly check-in.
    """
    detected_plate, confidence = ai_service.recognize_plate_demo()
    result = process_checkin(
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
        message=f"{result.message} (gate={payload.gate_id or 'unknown'})",
    )


@app.post("/api/esp/manual-open")
def handle_manual_open(payload: schemas.ManualOpenRequest):
    # á»ž báº£n demo chá»‰ log láº¡i, sau nÃ y cÃ³ thá»ƒ lÆ°u DB
    return {
        "status": "ok",
        "device_id": payload.device_id,
        "reason": payload.reason,
        "time": datetime.utcnow().isoformat(),
    }


@app.post("/api/esp/rfid", response_model=schemas.EspRfidResponse)
def handle_esp_rfid(
    payload: schemas.EspRfidRequest, db: Session = Depends(get_db)
):
    """
    Xac thuc UID RFID tu ESP32.
    Whitelist duoc luu trong SystemConfig key='rfid_uid_whitelist'
    theo dinh dang: UID1,UID2,UID3
    """
    uid_norm = payload.uid.strip().upper().replace(" ", "")
    whitelist_raw = get_config_text(db, "rfid_uid_whitelist", "")
    whitelist = {
        item.strip().upper().replace(" ", "")
        for item in whitelist_raw.split(",")
        if item.strip()
    }

    allowed = uid_norm in whitelist if whitelist else False
    action = "open" if allowed else "ignore"
    message = "RFID hop le" if allowed else "RFID khong hop le"

    return schemas.EspRfidResponse(
        action=action,
        uid=uid_norm,
        message=message,
        direction=payload.direction,
        gate_id=payload.gate_id,
    )


@app.post("/api/esp/fire-alert", response_model=schemas.FireAlertResponse)
def handle_fire_alert(payload: schemas.FireAlertRequest):
    """
    Nhan canh bao chay tu ESP32.
    Ban hien tai: ghi nhan canh bao va yeu cau mo tat ca cong.
    """
    return schemas.FireAlertResponse(
        status="ok",
        action="open_all",
        message=payload.message or f"Fire alert from {payload.device_id}",
    )


# ============ AI â€“ RECOGNIZE PLATE ============
@app.post("/api/ai/recognize-plate", response_model=schemas.PlateRecognitionResult)
async def recognize_plate_endpoint(file: UploadFile = File(...)):
    """
    Endpoint Ä‘á»ƒ test riÃªng mÃ´-Ä‘un AI:
    - Nháº­n 1 file áº£nh tá»« Postman / frontend
    - Tráº£ vá» biá»ƒn sá»‘ + Ä‘á»™ tin cáº­y
    """
    image_bytes = await file.read()
    plate, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    return schemas.PlateRecognitionResult(plate=plate, confidence=confidence)


@app.post("/api/parking/check-in", response_model=schemas.ParkingCheckinResponse)
async def parking_check_in(
    file: UploadFile = File(...),
    direction: str = Form("in"),
    device_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Check-in tu webcam: nhan anh, nhan dien bien so, luu session.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")

    plate, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    plate = ai_service.normalize_plate(plate)
    image_path = save_upload_image(image_bytes, file.filename)

    result = process_checkin(
        db=db,
        plate=plate,
        confidence=confidence,
        direction=direction,
        image_path=image_path,
    )
    return result


# ============ CRUD VEHICLE ============
@app.post("/api/vehicles", response_model=schemas.Vehicle, status_code=status.HTTP_201_CREATED)
def create_vehicle(
    vehicle_in: schemas.VehicleCreate, db: Session = Depends(get_db)
):
    exists = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == vehicle_in.plate_number)
        .first()
    )
    if exists:
        raise HTTPException(
            status_code=400, detail="Biá»ƒn sá»‘ Ä‘Ã£ tá»“n táº¡i"
        )

    vehicle = models.Vehicle(**vehicle_in.dict())
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
        raise HTTPException(status_code=404, detail="Không tìm thấy xe")
    return vehicle


@app.patch("/api/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def update_vehicle(
    vehicle_id: int,
    vehicle_in: schemas.VehicleUpdate,
    db: Session = Depends(get_db),
):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Không tìm thấy xe")

    for field, value in vehicle_in.dict(exclude_unset=True).items():
        setattr(vehicle, field, value)

    db.commit()
    db.refresh(vehicle)
    return vehicle


@app.delete("/api/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Không tìm thấy xe")
    db.delete(vehicle)
    db.commit()
    return


# ============ SUBSCRIPTIONS ============
@app.post("/api/subscriptions", response_model=schemas.Subscription)
def create_subscription(
    sub_in: schemas.SubscriptionCreate, db: Session = Depends(get_db)
):
    vehicle = db.query(models.Vehicle).get(sub_in.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Xe không tồn tại")

    sub = models.Subscription(
        vehicle_id=sub_in.vehicle_id,
        start_date=sub_in.start_date,
        end_date=sub_in.end_date,
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@app.get("/api/subscriptions", response_model=List[schemas.Subscription])
def list_subscriptions(db: Session = Depends(get_db)):
    return db.query(models.Subscription).all()


# ============ PARKING CHECK-OUT ============
@app.post("/api/parking/check-out", response_model=schemas.ParkingCheckoutResponse)
def parking_check_out(
    payload: schemas.ParkingCheckoutRequest, db: Session = Depends(get_db)
):
    """
    Check-out cho xe vãng lai hoặc vé tháng:
    - Tìm phiên đang mở (time_out is NULL) theo biển số.
    - Gán time_out = now, tính fee theo thời gian gửi và đơn giá trong SystemConfig.
    """
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
            detail="Không tìm thấy phiên gửi đang mở cho biển số này",
        )

    price_config = (
        db.query(models.SystemConfig)
        .filter(models.SystemConfig.key == "price_per_hour")
        .first()
    )
    price_per_hour = float(price_config.value) if price_config else 5000.0

    session.time_out = now
    session.direction = "out"

    duration_seconds = (session.time_out - session.time_in).total_seconds()
    duration_hours = max(duration_seconds / 3600.0, 0.0)

    hours_rounded = int(duration_hours) if duration_hours.is_integer() else int(duration_hours) + 1
    if hours_rounded == 0:
        hours_rounded = 1

    session.fee = hours_rounded * price_per_hour

    db.commit()
    db.refresh(session)

    duration_minutes = int(duration_seconds // 60)

    return schemas.ParkingCheckoutResponse(
        session=session,
        duration_minutes=duration_minutes,
    )

# ============ DASHBOARD ============
@app.get("/api/dashboard", response_model=schemas.DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    today = datetime.utcnow().date()

    total_in_bay = (
        db.query(models.ParkingSession)
        .filter(models.ParkingSession.time_out.is_(None))
        .count()
    )

    today_total_in = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.direction == "in",
            models.ParkingSession.time_in >= datetime(today.year, today.month, today.day),
        )
        .count()
    )

    today_total_out = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.direction == "out",
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out
            >= datetime(today.year, today.month, today.day),
        )
        .count()
    )

    today_revenue = (
        db.query(models.ParkingSession.fee)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out
            >= datetime(today.year, today.month, today.day),
        )
    )
    total_fee = sum(row[0] for row in today_revenue)

    return schemas.DashboardStats(
        total_in_bay=total_in_bay,
        today_total_in=today_total_in,
        today_total_out=today_total_out,
        today_revenue=total_fee,
    )

