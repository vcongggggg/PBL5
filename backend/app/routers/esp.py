from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from .. import schemas
from ..database import get_db
from ..services.gate_logic import bg_process_esp_event
from ..core.security import verify_api_key
from .. import state

import logging
import time as time_module
import uuid
from .. import models
from ..core.time_utils import get_vietnam_now
from ..services.parking_service import get_rfid_card
from ..services.config_service import get_config_text
from ..services import ai_service
from ..services.gate_logic import process_gate_scan, handle_critical_fire_gate_open
from ..services.fire_service import set_fire_alarm_active
from ..services.realtime import notify_clients

logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/api/esp/register")
def register_esp_ip(request: Request):
    """
    ESP32 gui thong tin IP len Backend khi khoi dong xong hoac ket noi lai Wi-Fi.
    """
    
    state.esp32_ip = request.client.host
    logger.info(f"ESP32 registered IP address: {state.esp32_ip}")
    return {"status": "ok", "state.esp32_ip": state.esp32_ip, "message": "Dang ky IP thanh cong"}




@router.post("/api/esp/events", response_model=schemas.EspEventResponse)
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
    
    state.esp32_ip = request.client.host
    
    direction = payload.direction or "in"
    gate_type = "entry" if direction == "in" else "exit"
    now = time_module.time()
    
    # Kiểm tra cooldown
    last_time = state._esp_event_cooldown.get(direction, 0)
    if now - last_time < state.ESP_EVENT_COOLDOWN_SECONDS:
        remaining = round(state.ESP_EVENT_COOLDOWN_SECONDS - (now - last_time), 1)
        return schemas.EspEventResponse(
            action="cooldown",
            plate="",
            vehicle_type="",
            message=f"Cooldown {remaining}s. Vui long doi.",
        )
    
    state._esp_event_cooldown[direction] = now
    
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




@router.post("/api/esp/manual-open")
def handle_manual_open(payload: schemas.ManualOpenRequest):
    return {
        "status": "ok",
        "device_id": payload.device_id,
        "reason": payload.reason,
        "time": get_vietnam_now().isoformat(),
    }




@router.post("/api/esp/rfid", response_model=schemas.EspRfidResponse)
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
    
    state.esp32_ip = request.client.host
    
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
    # Chỉ xóa pending scan khi cổng được mở thành công (action == "open")
    # Nếu validation thất bại (vd: sai thẻ, hết hạn, biển mờ), giữ lại pending scan 
    # để người dùng có thể quẹt thẻ lại hoặc quét lại mà không cần lùi xe kích hoạt cảm biến.
    should_delete_pending = (result.action == "open")
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




@router.post("/api/esp/fire-alert", response_model=schemas.FireAlertResponse)
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


