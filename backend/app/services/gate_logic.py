import time as time_module
import uuid
import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session

from .. import models, schemas
from ..core.string_utils import levenshtein_distance
from ..core.time_utils import get_vietnam_now
from ..database import SessionLocal
from ..integrations.mqtt_manager import mqtt_manager
from ..services import ai_service, camera_service
from ..services.config_service import get_config_bool, get_config_text, get_system_config_value
from ..services.fire_service import is_fire_alarm_blocking, set_fire_alarm_active
from ..services.fire_telemetry_service import add_fire_telemetry
from ..services.image_storage import image_url_from_path
from fastapi import HTTPException
from ..services.image_storage import save_upload_image, crop_image_bytes_by_bbox
from ..services.parking_service import (
    build_capacity_status,
    calculate_fee,
    count_open_sessions_by_ticket_type,
    get_rfid_card,
    resolve_vehicle_type,
    resolve_session_ticket_type,
    validate_rfid_for_scan,
)
from ..services.plate_tracker import plate_tracker
from ..services.realtime import notify_clients

logger = logging.getLogger("uvicorn")

_esp_event_cooldown = {}
ESP_EVENT_COOLDOWN_SECONDS = 2
PLATE_SCAN_WINDOW_SECONDS = 3.0
PLATE_SCAN_INTERVAL_SECONDS = 0.35
MSG_EXIT_NEEDS_MANUAL_REVIEW = "Camera không đọc được biển số hoặc ảnh mờ. Bảo vệ cần xác nhận thủ công để cho xe ra."
_pending_rfid_scans = {}
_rfid_scan_lock = asyncio.Lock()

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
    if trigger_type != "manual" and is_fire_alarm_blocking(db):
        return schemas.GateScanResponse(
            action="ignore",
            gate_type=gate_type,
            trigger_type=trigger_type,
            recognized_plate="UNKNOWN",
            confidence=0.0,
            valid_plate=False,
            matched=False,
            rfid_tag=rfid_tag,
            message="Đang báo cháy, hệ thống tạm dừng luồng xe thường. Cổng vào/ra đang được giữ mở.",
        )

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
        if recognized_plate and recognized_plate != "UNKNOWN":
            open_session = (
                db.query(models.ParkingSession)
                .filter(
                    models.ParkingSession.rfid_tag == rfid_tag,
                    models.ParkingSession.plate_number == recognized_plate,
                    models.ParkingSession.time_out.is_(None),
                )
                .order_by(models.ParkingSession.time_in.desc())
                .first()
            )
        if not open_session:
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

    # RFID alone is not enough to auto-close an exit session. The system only
    # opens automatically when the exit plate matches exactly or is within the
    # strict fuzzy threshold below. Unreadable or mismatched plates require an
    # operator to choose a manual reason and release the vehicle.

    plate_in_image_url = image_url_from_path(open_session.image_path) if open_session else None

    # Calculate Levenshtein distance early if we have a valid open session and some text is read
    # Also detect flipped plate: if reversing the exit plate (+ swapping 6↔9) gives a
    # closer match to plate_in, the OCR likely read the plate upside-down.
    plate_distance = 999
    if open_session and recognized_plate and recognized_plate != "UNKNOWN":
        plate_in_norm = ai_service.normalize_plate(open_session.plate_number)
        plate_distance = levenshtein_distance(plate_in_norm, recognized_plate)

        # Try un-flipping: reverse text + swap 6↔9
        _flip_map = str.maketrans("69", "96")
        flipped_plate = recognized_plate[::-1].translate(_flip_map)
        flipped_distance = levenshtein_distance(plate_in_norm, flipped_plate)

        if flipped_distance < plate_distance:
            logger.info(
                "EXIT plate flip detected: OCR read '%s' (distance=%d) → corrected to '%s' (distance=%d) based on entry plate '%s'",
                recognized_plate, plate_distance, flipped_plate, flipped_distance, plate_in_norm,
            )
            recognized_plate = flipped_plate
            plate_distance = flipped_distance

    MAX_PLATE_DISTANCE = 1  # Cho phép tối đa sai 1 ký tự
    MAX_RFID_ASSISTED_DISTANCE = 2  # RFID trợ giúp: tối đa lệch 2 ký tự (lệch ≥3 = xe khác)
    rfid_matches_session = bool(
        trigger_type == "rfid"
        and rfid_card
        and open_session
        and open_session.rfid_card_id
        and open_session.rfid_card_id == rfid_card.id
    )
    is_rfid_assisted_bypass = bool(
        rfid_matches_session
        and plate_distance <= MAX_RFID_ASSISTED_DISTANCE
    )
    is_rfid_assisted = bool(
        rfid_matches_session
        and MAX_PLATE_DISTANCE < plate_distance <= MAX_RFID_ASSISTED_DISTANCE
    )

    # 1. Trường hợp không đọc được bất kỳ chữ nào (Ảnh mờ hoàn toàn hoặc UNKNOWN)
    if not recognized_plate or recognized_plate == "UNKNOWN":
        msg = MSG_EXIT_NEEDS_MANUAL_REVIEW
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": "UNKNOWN",
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in": open_session.plate_number if open_session else None,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            plate_in=open_session.plate_number if open_session else None,
            plate_out="UNKNOWN",
            recognized_plate="UNKNOWN",
            confidence=confidence,
            valid_plate=False,
            matched=False,
            image_url=image_url,
            plate_in_image_url=plate_in_image_url,
            message=msg,
        )

    # 2. Trường hợp đọc được chữ nhưng không hợp lệ (ví dụ bị che mất chữ nên ngắn hơn 7 ký tự)
    # và không có RFID trợ giúp khớp trong khoảng cách cho phép
    if (not valid_plate or confidence < threshold) and not is_rfid_assisted_bypass:
        if not open_session:
            msg = "Không tìm thấy thông tin xe vào (Thẻ này chưa được dùng)"
        else:
            msg = f"Biển số ra KHÔNG KHỚP — lệch {plate_distance} ký tự (VÀO: {open_session.plate_number}, RA: {recognized_plate}). Bảo vệ cần xác nhận thủ công để cho xe ra."
        
        await notify_clients("parking_update", {
            "action": "ignore",
            "gate_type": "exit",
            "plate": recognized_plate,
            "rfid_tag": rfid_tag,
            "confidence": confidence,
            "image_url": image_url,
            "plate_in": open_session.plate_number if open_session else None,
            "plate_in_image_url": plate_in_image_url,
            "message": msg,
        })
        return schemas.GateScanResponse(
            action="ignore",
            gate_type="exit",
            trigger_type=trigger_type,
            plate_in=open_session.plate_number if open_session else None,
            plate_out=recognized_plate,
            recognized_plate=recognized_plate,
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
    if plate_distance > MAX_PLATE_DISTANCE and not is_rfid_assisted:
        msg = f"Biển số ra KHÔNG KHỚP — lệch {plate_distance} ký tự (VÀO: {open_session.plate_number}, RA: {recognized_plate}). Bảo vệ cần xác nhận thủ công để cho xe ra."
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
    if is_rfid_assisted:
        open_session.match_status = "rfid_assisted"
    else:
        open_session.match_status = "matched" if plate_distance == 0 else "fuzzy_matched"

    # Cập nhật trạng thái thẻ RFID thành "available" khi ra thành công
    rfid_card_to_release = rfid_card or get_rfid_card(db, open_session.rfid_tag)
    if rfid_card_to_release:
        rfid_card_to_release.status = "available"

    db.commit()
    db.refresh(open_session)

    plate_in_display = open_session.plate_in or open_session.plate_number
    if is_rfid_assisted:
        success_msg = f"Biển số ra lệch {plate_distance} ký tự so với biển vào (VÀO: {plate_in_display}, RA: {recognized_plate}). RFID khớp nên cho phép xe ra."
    elif plate_distance == 0:
        success_msg = f"Biển số ra trùng khớp 100% biển vào ({plate_in_display}), cho phép xe ra"
    else:
        success_msg = f"Biển số ra khớp trong ngưỡng cho phép: lệch {plate_distance} ký tự so với biển vào (VÀO: {plate_in_display}, RA: {recognized_plate}), cho phép xe ra"

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


gate_locks = {
    "entry": asyncio.Lock(),
    "exit": asyncio.Lock(),
}
PLATE_SCAN_WINDOW_SECONDS = 3.0
PLATE_SCAN_INTERVAL_SECONDS = 0.35
_manual_gate_open_until = {"entry": 0.0, "exit": 0.0}

FIRE_GATE_OPEN_COOLDOWN_SECONDS = 30.0
_last_fire_gate_open_at = 0.0

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

async def process_rfid_swipe(
    db: Session,
    uid: str,
    device_id: str,
    direction_hint: str = "in",
    gate_id: Optional[str] = None,
    is_http: bool = False
) -> dict:
    """
    Xử lý quẹt thẻ RFID (dùng chung cho cả MQTT và HTTP API).
    Trả về dict chứa thông tin kết quả để phản hồi cho caller.
    """
    uid_norm = uid.strip().upper().replace(" ", "").replace(":", "")
    if not uid_norm:
        return {
            "action": "ignore",
            "uid": "",
            "message": "Mã thẻ RFID trống",
            "direction": direction_hint,
            "gate_type": "entry",
        }

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

    # 3. Kiểm tra hàng đợi quét biển số ở cả 2 hướng (< 45 giây)
    pending_entry = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
    pending_exit = db.query(models.PendingScan).filter(models.PendingScan.gate_type == "exit").first()
    
    now_dt = get_vietnam_now()
    EXPIRE_SECONDS = 120
    
    active_entry = pending_entry if (pending_entry and (now_dt - pending_entry.created_at).total_seconds() <= EXPIRE_SECONDS) else None
    active_exit = pending_exit if (pending_exit and (now_dt - pending_exit.created_at).total_seconds() <= EXPIRE_SECONDS) else None
    
    direction_hint_norm = (direction_hint or "").strip().lower()
    gate_id_norm = (gate_id or "").strip().lower()
    hinted_gate_type = None
    if direction_hint_norm == "out" or gate_id_norm.endswith("out"):
        hinted_gate_type = "exit"
    elif direction_hint_norm == "in" or gate_id_norm.endswith("in"):
        hinted_gate_type = "entry"
    
    # Giải quyết hướng thực tế dựa trên các queue có xe đang chờ
    resolved_gate_type = None
    if active_entry and not active_exit:
        resolved_gate_type = "entry"
    elif active_exit and not active_entry:
        resolved_gate_type = "exit"
    elif active_entry and active_exit:
        resolved_gate_type = hinted_gate_type or ("entry" if logical_direction == "in" else "exit")
    else:
        # Fallback về hướng payload gửi lên hoặc gợi ý
        resolved_gate_type = hinted_gate_type or ("entry" if logical_direction == "in" else "exit")

    direction = "in" if resolved_gate_type == "entry" else "out"
    gate_type = resolved_gate_type
    
    pending = active_entry if gate_type == "entry" else active_exit

    if not pending and gate_type == "entry" and card and card.status == "in_use":
        result_payload = {
            "action": "ignore",
            "uid": uid_norm,
            "message": "Thẻ RFID đang được sử dụng bởi xe khác",
            "direction": direction,
            "gate_id": gate_id,
        }
        if not is_http:
            await notify_clients("parking_update", {
                "action": "ignore",
                "gate_type": gate_type,
                "plate": "UNKNOWN",
                "rfid_tag": uid_norm,
                "confidence": 0.0,
                "matched": False,
                "message": "Thẻ RFID đang được sử dụng bởi xe khác",
            })
        return result_payload

    # 4. Dự phòng cho cổng ra: nếu camera hỏng/không có pending_scan nhưng thẻ có open session -> Cho phép ra (UNKNOWN plate fallback)
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
        if result.action == "open" and not is_http:
            mqtt_manager.publish_open_gate(device_id, direction)
        
        result_payload = {
            "action": result.action,
            "uid": uid_norm,
            "message": result.message,
            "direction": direction,
            "gate_id": gate_id,
        }
        if not is_http:
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
        return result_payload

    if not pending:
        result_payload = {
            "action": "ignore",
            "uid": uid_norm,
            "message": "Vui lòng đỗ xe đúng vị trí cảm biến trước khi quẹt thẻ",
            "direction": direction,
            "gate_id": gate_id,
        }
        if not is_http:
            await notify_clients("parking_update", {
                "action": "ignore",
                "gate_type": gate_type,
                "plate": "UNKNOWN",
                "confidence": 0.0,
                "message": "Vui lòng đỗ xe đúng vị trí cảm biến trước khi quẹt thẻ",
            })
        return result_payload

    # 5. Nếu AI vẫn đang PROCESSING -> Đưa vào hàng chờ quẹt sớm (Protected by Lock)
    if pending.plate_number == "PROCESSING":
        logger.info(f"RFID early swipe detected for {gate_type}. Storing in _pending_rfid_scans.")
        async with _rfid_scan_lock:
            _pending_rfid_scans[gate_type] = (uid_norm, device_id, now_dt)
        
        message_processing = "Đang nhận diện biển số, vui lòng đợi 2-3 giây rồi quẹt lại" if is_http else "Đang nhận dạng biển số, vui lòng giữ nguyên vị trí, cổng sẽ mở tự động..."
        if not is_http:
            await notify_clients("pending_scan", {
                "gate_type": gate_type,
                "recognized_plate": "PROCESSING",
                "confidence": 0.0,
                "message": "Đang nhận dạng biển số, vui lòng giữ nguyên vị trí, cổng sẽ mở tự động..."
            })
        return {
            "action": "ignore" if is_http else "processing",
            "uid": uid_norm,
            "message": message_processing,
            "direction": direction,
            "gate_id": gate_id,
        }

    # 6. Nếu đã xử lý xong AI, gọi hàm validation bình thường
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

    if result.action == "open" and not is_http:
        mqtt_manager.publish_open_gate(device_id, direction)

    result_payload = {
        "action": result.action,
        "uid": uid_norm,
        "message": result.message,
        "direction": direction,
        "gate_id": gate_id,
    }

    if not is_http:
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

    # Chỉ xóa pending scan khi cổng được mở thành công (action == "open")
    should_delete_pending = (result.action == "open")
    if should_delete_pending:
        db.delete(pending)
        db.commit()

    return result_payload

async def process_mqtt_rfid_validation(db: Session, pending, uid_norm: str, gate_type: str, device_id: str, direction: str):
    # Delegate to the unified process_rfid_swipe function to avoid code duplication
    await process_rfid_swipe(
        db=db,
        uid=uid_norm,
        device_id=device_id,
        direction_hint=direction,
        gate_id=gate_type,
        is_http=False
    )

async def handle_mqtt_event(device_id: str, event_type: str, payload: dict):
    """
    Xử lý các sự kiện bất đồng bộ từ ESP32 qua giao thức MQTT.
    """
    db = SessionLocal()
    try:
        if event_type in ["car_detected", "rfid_scan"] and is_fire_alarm_blocking(db):
            await notify_clients("parking_update", {
                "action": "ignore",
                "gate_type": "fire",
                "plate": "UNKNOWN",
                "confidence": 0.0,
                "matched": False,
                "message": "Đang báo cháy, bỏ qua luồng xe/thẻ. Cổng vào/ra đang được giữ mở.",
            })
            return

        if event_type == "car_detected":
            direction = payload.get("direction", "in")
            gate_type = "entry" if direction == "in" else "exit"
            now = time_module.time()

            # Kiểm tra cooldown
            last_time = _esp_event_cooldown.get(direction, 0)
            if now - last_time < ESP_EVENT_COOLDOWN_SECONDS:
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
            await process_rfid_swipe(db, uid, device_id, direction_hint, gate_id, is_http=False)

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

        elif event_type == "fire_telemetry":
            point = add_fire_telemetry(
                device_id=device_id,
                digital_value=payload.get("digital_value", 1),
                analog_value=payload.get("analog_value", payload.get("sensor_value", 0)),
                fire_detected=payload.get("fire_detected", False),
                fire_alert_active=payload.get("fire_alert_active", False),
            )
            await notify_clients("fire_telemetry", point)

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
    lock = gate_locks.setdefault(gate_type, asyncio.Lock())
    async with lock:
        db_session = SessionLocal()
        try:
            # Kiểm tra xem có bị overwrite bởi event mới hơn không
            pending = db_session.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).first()
            if not pending or pending.scan_token != scan_token:
                logger.info(f"Background task for {gate_type} superseded. Discarding results.")
                return

            valid_plate = ai_service.is_valid_vn_plate(recognized_plate)
            threshold = get_system_config_value(db_session, "plate_confidence_threshold", 0.6)

            # Ở làn vào, nếu biển số không hợp lệ/mờ/UNKNOWN -> vẫn giữ pending scan nhưng thông báo lỗi để người dùng biết và quét lại/quẹt thẻ
            if gate_type == "entry" and (not valid_plate or confidence < threshold or recognized_plate == "UNKNOWN"):
                msg = "Biển số vào không hợp lệ hoặc ảnh mờ. Vui lòng quét lại hoặc thử quẹt thẻ."
                
                # Vẫn lưu pending scan để người dùng có thể kích hoạt từ xa hoặc thử lại
                pending.plate_number = recognized_plate
                pending.confidence = confidence
                pending.image_path = image_path
                db_session.commit()
                
                await notify_clients("pending_scan", {
                    "gate_type": "entry",
                    "recognized_plate": recognized_plate or "UNKNOWN",
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
            async with _rfid_scan_lock:
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

