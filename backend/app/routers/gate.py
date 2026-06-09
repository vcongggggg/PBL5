from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Form, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import schemas, models
from ..database import get_db
from ..services.gate_logic import handle_mqtt_event, process_gate_scan
from ..state import gate_locks, _manual_gate_open_until, _manual_gate_open_until
from ..core.security import verify_api_key
from ..services.parking_service import normalize_manual_reason
from ..services.config_service import get_system_config_value
import time as time_module
from ..integrations.mqtt_manager import mqtt_manager

import logging
import uuid
import asyncio
from ..services.fire_service import is_fire_alarm_blocking
from ..services.parking_service import get_rfid_card
from ..core.time_utils import get_vietnam_now
from ..services import camera_service
from ..services.gate_logic import bg_process_esp_event
from ..services.parking_service import create_manual_gate_log
from ..services.realtime import notify_clients
MSG_GATE_OPEN_WAIT = "Cổng {gate_type} đang mở thủ công. Vui lòng đợi thêm {remaining}s."
MSG_MANUAL_OPEN_MQTT = "Đã gửi lệnh mở cổng thủ công qua MQTT thành công."
MSG_MANUAL_OPEN_HTTP = "Đã gửi lệnh mở cổng thủ công qua HTTP dự phòng thành công."
logger = logging.getLogger(__name__)


MANUAL_GATE_OPEN_SECONDS = 15.0

router = APIRouter()


@router.post("/api/gates/trigger", response_model=schemas.GateTriggerResponse)
def gate_trigger(payload: schemas.GateTriggerRequest, db: Session = Depends(get_db)):
    gate_type = payload.gate_type.lower()
    trigger_type = payload.trigger_type.lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    if trigger_type not in ["sensor", "rfid"]:
        raise HTTPException(status_code=400, detail="trigger_type must be sensor or rfid")
    if is_fire_alarm_blocking(db):
        raise HTTPException(
            status_code=423,
            detail="Đang báo cháy, hệ thống tạm dừng nhận xe thường. Cổng vào/ra đang được giữ mở.",
        )

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




@router.post("/api/gates/scan-from-cam", response_model=schemas.GateScanResponse)
async def gate_scan_from_cam(
    gate_type: str = Form("entry"),
    trigger_type: str = Form("sensor"),
    source_id: Optional[str] = Form(None),
    rfid_tag: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    image_bytes = camera_service.capture_image(gate_type)
    if not image_bytes:
        raise HTTPException(status_code=500, detail="Không thể lấy ảnh từ Camera")
    return await process_gate_scan(
        db=db, image_bytes=image_bytes, filename=f"auto_{gate_type}.jpg",
        gate_type=gate_type, trigger_type=trigger_type, source_id=source_id, rfid_tag=rfid_tag
    )



@router.post("/api/gates/scan", response_model=schemas.GateScanResponse)
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




@router.post("/api/gates/sensor-event")
async def gate_sensor_event(payload: schemas.GateTriggerRequest, db: Session = Depends(get_db)):
    gate_type = payload.gate_type.lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    if is_fire_alarm_blocking(db):
        raise HTTPException(
            status_code=423,
            detail="Đang báo cháy, hệ thống tạm dừng cảm biến xe. Cổng vào/ra đang được giữ mở.",
        )

    direction = "in" if gate_type == "entry" else "out"
    scan_token = uuid.uuid4().hex
    device_id = payload.source_id or f"{gate_type}-sensor-ui"

    try:
        db.query(models.PendingScan).filter(models.PendingScan.gate_type == gate_type).delete()
        pending = models.PendingScan(
            gate_type=gate_type,
            plate_number="PROCESSING",
            confidence=0.0,
            image_path=None,
            device_id=device_id,
            scan_token=scan_token,
        )
        db.add(pending)
        db.commit()
    except Exception as e:
        logger.error(f"Error inserting PROCESSING pending scan from UI sensor: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Khong the tao phien quet cam bien")

    asyncio.create_task(
        bg_process_esp_event(
            direction=direction,
            gate_type=gate_type,
            device_id=device_id,
            scan_token=scan_token,
        )
    )

    await notify_clients("pending_scan", {
        "gate_type": gate_type,
        "recognized_plate": "PROCESSING",
        "confidence": 0.0,
        "message": "Đang bám biển số, vui lòng giữ xe trong vùng camera...",
    })

    return {
        "status": "processing",
        "gate_type": gate_type,
        "direction": direction,
        "scan_token": scan_token,
        "message": "Đã kích hoạt cảm biến giả lập, hệ thống đang bám biển số.",
    }




@router.post("/api/gates/force-open")
async def force_open_gate(
    gate_type: str = Form(...),
    reason: str = Form("manual_override"),
    operator: str = Form("operator"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key),
):
    """
    Gui lenh mo cong thu cong tu Web UI toi ESP32.
    Neu cong dang trong thoi gian mo thu cong thi khong gui lenh lap lai.
    """
    gate_type = (gate_type or "").lower()
    if gate_type not in ["entry", "exit"]:
        raise HTTPException(status_code=400, detail="gate_type must be entry or exit")
    reason = normalize_manual_reason(reason)

    gate = "in" if gate_type == "entry" else "out"
    manual_gate_open_seconds = get_system_config_value(db, "manual_gate_open_seconds", MANUAL_GATE_OPEN_SECONDS)
    now = time_module.time()
    open_until = _manual_gate_open_until.get(gate_type, 0.0)
    if now < open_until:
        remaining = max(1, int(open_until - now + 0.999))
        message = MSG_GATE_OPEN_WAIT.format(gate_type=gate_type, remaining=remaining)
        await notify_clients("parking_update", {
            "action": "gate_open",
            "gate_type": gate_type,
            "message": message,
        })
        return {
            "status": "gate_open",
            "gate_type": gate_type,
            "remaining_seconds": remaining,
            "message": message,
        }

    if mqtt_manager.is_connected:
        mqtt_manager.publish_open_gate("esp32-barrier-01", gate)
        _manual_gate_open_until[gate_type] = time_module.time() + manual_gate_open_seconds
        create_manual_gate_log(db, gate_type, "open_manual", reason=reason, operator=operator, source="web_mqtt")
        message = MSG_MANUAL_OPEN_MQTT
        await notify_clients("parking_update", {
            "action": "open_manual",
            "gate_type": gate_type,
            "reason": reason,
            "message": message,
        })
        return {"status": "ok", "message": message, "reason": reason}

    import app.state as state
    if not state.esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 chua ket noi hoac chua cap nhat IP len Backend."
        )

    esp_url = f"http://{state.esp32_ip}/open-gate?gate={gate}"

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
        _manual_gate_open_until[gate_type] = time_module.time() + manual_gate_open_seconds
        create_manual_gate_log(db, gate_type, "open_manual", reason=reason, operator=operator, source="web_http")
        message = MSG_MANUAL_OPEN_HTTP.format(gate_type=gate_type)
        await notify_clients("parking_update", {
            "action": "open_manual",
            "gate_type": gate_type,
            "reason": reason,
            "message": message,
        })
        return {"status": "ok", "message": message, "reason": reason}

    raise HTTPException(
        status_code=502,
        detail=f"Khong the ket noi hoac loi phan hoi tu ESP32: {body}"
    )




@router.get("/api/gates/manual-open-logs", response_model=List[schemas.ManualGateLog])
def list_manual_gate_logs(limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(models.ManualGateLog)
        .order_by(models.ManualGateLog.created_at.desc(), models.ManualGateLog.id.desc())
        .limit(limit)
        .all()
    )


