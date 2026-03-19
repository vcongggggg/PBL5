from datetime import datetime
from typing import List

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from . import ai_service, models, schemas
from .database import Base, engine, get_db

# Khởi tạo DB
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PBL5 Smart Parking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    Endpoint ESP32 gọi khi cảm biến phát hiện xe.
    Ở phiên bản demo, logic AI / nhận diện biển số sẽ được giả lập.
    """

    # TODO: tích hợp AI (YOLO + OCR) để đọc biển số thật.
    # Hiện tại gọi hàm demo trả về biển số giả định.
    detected_plate, _ = ai_service.recognize_plate_demo()

    # Tìm xe đăng ký vé tháng theo biển số
    vehicle = (
        db.query(models.Vehicle)
        .filter(models.Vehicle.plate_number == detected_plate)
        .first()
    )

    vehicle_type = "unknown"
    message = "Khach vang lai"
    now = datetime.utcnow()

    if vehicle:
        # Kiểm tra vé tháng còn hạn
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

    # Tạo bản ghi phiên gửi xe
    session = models.ParkingSession(
        vehicle_id=vehicle.id if vehicle else None,
        plate_number=detected_plate,
        direction=payload.direction,
        time_in=now,
        fee=0,
    )
    db.add(session)
    db.commit()

    return schemas.EspEventResponse(
        action="open",
        plate=detected_plate,
        vehicle_type=vehicle_type,
        message=message,
    )


@app.post("/api/esp/manual-open")
def handle_manual_open(payload: schemas.ManualOpenRequest):
    # Ở bản demo chỉ log lại, sau này có thể lưu DB
    return {
        "status": "ok",
        "device_id": payload.device_id,
        "reason": payload.reason,
        "time": datetime.utcnow().isoformat(),
    }


# ============ AI – RECOGNIZE PLATE ============
@app.post("/api/ai/recognize-plate", response_model=schemas.PlateRecognitionResult)
async def recognize_plate_endpoint(file: UploadFile = File(...)):
    """
    Endpoint để test riêng mô-đun AI:
    - Nhận 1 file ảnh từ Postman / frontend
    - Trả về biển số + độ tin cậy
    """
    image_bytes = await file.read()
    plate, confidence = ai_service.recognize_plate_from_bytes(image_bytes)
    return schemas.PlateRecognitionResult(plate=plate, confidence=confidence)


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
            status_code=400, detail="Biển số đã tồn tại"
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
            detail="Không tìm thấy phiên gửi xe đang mở cho biển số này",
        )

    # Lấy đơn giá từ SystemConfig, key = price_per_hour, mặc định 5000 VND/giờ
    price_config = (
        db.query(models.SystemConfig)
        .filter(models.SystemConfig.key == "price_per_hour")
        .first()
    )
    price_per_hour = float(price_config.value) if price_config else 5000.0

    session.time_out = now
    # Đổi trạng thái lượt thành "out" sau khi check-out thành công
    session.direction = "out"

    duration_seconds = (session.time_out - session.time_in).total_seconds()
    duration_hours = max(duration_seconds / 3600.0, 0.0)

    # Tính tiền: làm tròn lên theo giờ
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

