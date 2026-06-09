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
from ..services.gate_logic import process_gate_scan, handle_critical_fire_gate_open, process_rfid_swipe
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
    direction_hint = payload.direction or "in"
    
    result = await process_rfid_swipe(
        db=db,
        uid=payload.uid,
        device_id=payload.device_id,
        direction_hint=direction_hint,
        gate_id=payload.gate_id,
        is_http=True
    )
    
    return schemas.EspRfidResponse(
        action=result["action"],
        uid=result.get("uid") or payload.uid.strip().upper().replace(" ", "").replace(":", ""),
        message=result["message"],
        direction=result["direction"],
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


