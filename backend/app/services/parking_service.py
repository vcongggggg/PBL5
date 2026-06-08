from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from .. import models, schemas
from . import ai_service
from .config_service import get_system_config_value
from ..core.string_utils import levenshtein_distance
from ..core.time_utils import get_vietnam_date, get_vietnam_now


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


def build_capacity_status(
    total_in_bay: int,
    max_slots: int,
    near_full_threshold: float = 0.7,
    almost_full_threshold: float = 0.9,
) -> dict:
    safe_max_slots = max(0, int(max_slots or 0))
    if safe_max_slots == 0:
        return {
            "max_slots": 0,
            "available_slots": 0,
            "occupancy_percent": 100.0,
            "capacity_status": "full",
            "capacity_message": "Bai xe da day (0/0). Tam dung nhan xe vao.",
            "near_full_threshold": near_full_threshold,
            "almost_full_threshold": almost_full_threshold,
        }
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


def calculate_fee(
    now: datetime,
    session: models.ParkingSession,
    db: Session,
    ticket_type: str = "guest",
) -> Tuple[int, float]:
    duration_seconds = (now - session.time_in).total_seconds()
    duration_minutes = int(duration_seconds // 60)

    if ticket_type == "monthly":
        return duration_minutes, 0.0

    price_per_hour = get_system_config_value(db, "price_per_hour", 5000.0)
    duration_hours = max(duration_seconds / 3600.0, 0.0)

    hours_rounded = int(duration_hours) if duration_hours.is_integer() else int(duration_hours) + 1
    if hours_rounded == 0:
        hours_rounded = 1

    fee = hours_rounded * price_per_hour
    return duration_minutes, fee


def normalize_manual_reason(reason: str) -> str:
    allowed_reasons = {
        "verified_plate",
        "verified_entry",
        "lost_card",
        "system_error",
        "manual_override",
        "emergency",
        "maintenance",
    }
    reason_norm = (reason or "manual_override").strip().lower()
    return reason_norm if reason_norm in allowed_reasons else "manual_override"


def get_lost_rfid_compensation_fee(db: Session) -> float:
    return max(0.0, get_system_config_value(db, "lost_rfid_compensation_fee", 50000.0))


def resolve_session_ticket_type(db: Session, session: models.ParkingSession) -> str:
    if session.rfid_card_type == "guest":
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

    check_date = get_vietnam_date()
    has_monthly = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.vehicle_id == vehicle_id,
            models.Subscription.is_active == True,  # noqa: E712
            models.Subscription.start_date <= check_date,
            models.Subscription.end_date >= check_date,
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
        registered_vehicle = card.vehicle
        if not registered_vehicle:
            return None, "The thang chua duoc gan cho phuong tien nao"

        if recognized_plate and recognized_plate != "UNKNOWN":
            plate_distance = levenshtein_distance(
                ai_service.normalize_plate(registered_vehicle.plate_number),
                recognized_plate,
            )
            if plate_distance > 1:
                return None, f"Bien so dang quet ({recognized_plate}) khong khop voi dang ky ve thang ({registered_vehicle.plate_number})"

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
            if gate_type == "exit":
                registered_plate = ai_service.normalize_plate(registered_vehicle.plate_number)
                open_session = (
                    db.query(models.ParkingSession)
                    .filter(
                        models.ParkingSession.time_out.is_(None),
                        (
                            (models.ParkingSession.rfid_card_id == card.id)
                            | (models.ParkingSession.rfid_tag == card.card_uid)
                            | (models.ParkingSession.plate_number == registered_plate)
                        ),
                    )
                    .first()
                )
                if open_session:
                    return card, None
            return None, "Dang ky ve thang da het han hoac khong hoat dong"
        if card.monthly_user_id and active_sub.monthly_user_id and card.monthly_user_id != active_sub.monthly_user_id:
            return None, "The RFID khong khop chu dang ky ve thang"

    return card, None


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
