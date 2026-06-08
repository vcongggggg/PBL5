from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from .. import models, schemas
from ..database import get_db

from ..services import ai_service
from ..core.time_utils import get_vietnam_date, get_vietnam_now
from datetime import time as dt_time


router = APIRouter()

# ============ CRUD VEHICLE ============
@router.post("/api/vehicles", response_model=schemas.Vehicle, status_code=status.HTTP_201_CREATED)
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


@router.get("/api/vehicles", response_model=List[schemas.Vehicle])
def list_vehicles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Vehicle).offset(skip).limit(limit).all()


@router.get("/api/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
def get_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Khong tim thay xe")
    return vehicle


@router.patch("/api/vehicles/{vehicle_id}", response_model=schemas.Vehicle)
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


@router.delete("/api/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(vehicle_id: int, db: Session = Depends(get_db)):
    vehicle = db.query(models.Vehicle).get(vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Khong tim thay xe")
    db.delete(vehicle)
    db.commit()
    return


# ============ SUBSCRIPTIONS ============
@router.post("/api/subscriptions", response_model=schemas.Subscription)
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


@router.get("/api/subscriptions", response_model=List[schemas.Subscription])
def list_subscriptions(db: Session = Depends(get_db)):
    return db.query(models.Subscription).all()


@router.post("/api/monthly-registrations", response_model=schemas.MonthlyRegistrationResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/api/monthly-registrations", response_model=List[schemas.MonthlyRegistrationItem])
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


@router.delete("/api/monthly-registrations/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
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
@router.post("/api/monthly-users", response_model=schemas.MonthlyUser, status_code=status.HTTP_201_CREATED)
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


@router.get("/api/monthly-users", response_model=List[schemas.MonthlyUser])
def list_monthly_users(db: Session = Depends(get_db)):
    return db.query(models.MonthlyUser).order_by(models.MonthlyUser.id.desc()).all()


# ============ UTILS ============
# ============ RFID CARDS ============
@router.post("/api/rfid-cards", response_model=schemas.RFIDCard, status_code=status.HTTP_201_CREATED)
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


@router.get("/api/rfid-cards", response_model=List[schemas.RFIDCard])
def list_rfid_cards(db: Session = Depends(get_db)):
    return db.query(models.RFIDCard).order_by(models.RFIDCard.id.desc()).all()



