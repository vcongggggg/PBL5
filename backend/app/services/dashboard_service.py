from datetime import datetime

from sqlalchemy.orm import Session

from .. import models, schemas
from .config_service import get_system_config_value
from .parking_service import build_capacity_status, count_open_sessions_by_ticket_type
from ..core.time_utils import get_vietnam_date


def build_dashboard_stats(db: Session) -> schemas.DashboardStats:
    today = get_vietnam_date()
    start_of_day = datetime(today.year, today.month, today.day)

    total_in_bay = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_(None),
            models.ParkingSession.match_status != "ignored",
        )
        .count()
    )

    today_total_in = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_in >= start_of_day,
            models.ParkingSession.match_status != "ignored",
        )
        .count()
    )

    today_total_out = (
        db.query(models.ParkingSession)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
            models.ParkingSession.match_status != "ignored",
        )
        .count()
    )

    today_revenue = (
        db.query(models.ParkingSession.fee)
        .filter(
            models.ParkingSession.time_out.is_not(None),
            models.ParkingSession.time_out >= start_of_day,
            models.ParkingSession.match_status != "ignored",
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
