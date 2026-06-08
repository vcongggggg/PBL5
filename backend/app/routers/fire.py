from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db
from ..core.time_utils import get_vietnam_now
from ..services.gate_logic import handle_mqtt_event
from ..core.security import verify_api_key
from ..database import SessionLocal
from ..integrations.mqtt_manager import mqtt_manager
from .. import state
from ..services.realtime import notify_clients
from ..services.gate_logic import handle_critical_fire_gate_open
from ..services.fire_service import resolve_open_fire_alerts, is_fire_alarm_blocking

from ..services.fire_service import set_fire_alarm_active





router = APIRouter()

# ============ FIRE RESET (Tắt báo động cháy từ xa) ============
@router.post("/api/fire/reset")
async def reset_fire_alarm(api_key: str = Depends(verify_api_key)):
    """
    Gọi ESP32 để tắt chế độ báo động cháy (Ưu tiên MQTT, dự phòng HTTP).
    Chỉ bảo vệ mới được phép gọi sau khi xác nhận an toàn.
    """
    # 1. Gửi lệnh qua MQTT
    if mqtt_manager.is_connected:
        db = SessionLocal()
        try:
            resolved_count = resolve_open_fire_alerts(db)
        finally:
            db.close()
        mqtt_manager.publish_reset_fire("esp32-barrier-01")
        await notify_clients("fire_reset", {
            "message": "Đã tắt báo động cháy qua MQTT. Hệ thống trở lại trạng thái bình thường.",
            "resolved_count": resolved_count,
            "fire_active": False,
        })
        return {"status": "ok", "message": "Đã gửi lệnh tắt báo động cháy thành công qua MQTT.", "resolved_count": resolved_count}

    # 2. Gửi lệnh qua HTTP
    
    if not state.esp32_ip:
        raise HTTPException(
            status_code=503,
            detail="ESP32 offline (cả MQTT và HTTP Web Server đều không khả dụng).",
        )

    import urllib.request
    import urllib.error
    from fastapi.concurrency import run_in_threadpool

    def send_reset():
        try:
            req = urllib.request.Request(
                f"http://{state.esp32_ip}/reset-fire", method="GET"
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            return -1, str(e.reason)
        except Exception as e:
            return -1, str(e)

    code, body = await run_in_threadpool(send_reset)

    if code == 200:
        db = SessionLocal()
        try:
            resolved_count = resolve_open_fire_alerts(db)
        finally:
            db.close()
        await notify_clients("fire_reset", {
            "message": "Đã tắt báo động cháy qua HTTP. Hệ thống trở lại trạng thái bình thường.",
            "resolved_count": resolved_count,
            "fire_active": False,
        })
        return {"status": "ok", "message": "Đã gửi lệnh tắt báo động cháy thành công qua HTTP.", "resolved_count": resolved_count}
    else:
        raise HTTPException(
            status_code=502,
            detail=f"Không thể kết nối ESP32 để reset fire alarm: {body}",
        )
# ============ FIRE ALERTS ============
@router.post("/api/fire-alerts", response_model=schemas.FireAlert)
async def create_fire_alert(payload: schemas.FireAlertCreate, db: Session = Depends(get_db)):
    alert = models.FireAlert(
        sensor_id=payload.sensor_id,
        level=payload.level,
        message=payload.message,
    )
    db.add(alert)
    if payload.level == "critical":
        set_fire_alarm_active(db, True)
    db.commit()
    db.refresh(alert)

    gate_opened = handle_critical_fire_gate_open() if payload.level == "critical" else False
    
    # Thông báo hỏa hoạn qua WebSocket ngay lập tức
    await notify_clients("fire_alert", {
        "id": alert.id,
        "sensor_id": alert.sensor_id,
        "message": alert.message,
        "level": alert.level,
        "gate_opened": gate_opened,
    })
    
    return alert


@router.get("/api/fire-alerts", response_model=List[schemas.FireAlert])
def list_fire_alerts(
    unacked_only: bool = False,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    query = db.query(models.FireAlert)
    if unacked_only:
        query = query.filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
    return query.order_by(models.FireAlert.created_at.desc()).limit(limit).all()


@router.get("/api/fire/status", response_model=schemas.FireStatus)
def get_fire_status(db: Session = Depends(get_db)):
    unacknowledged_count = (
        db.query(models.FireAlert)
        .filter(models.FireAlert.is_acknowledged == False)  # noqa: E712
        .count()
    )
    critical_count = (
        db.query(models.FireAlert)
        .filter(
            models.FireAlert.is_acknowledged == False,  # noqa: E712
            models.FireAlert.level == "critical",
        )
        .count()
    )
    warning_count = (
        db.query(models.FireAlert)
        .filter(
            models.FireAlert.is_acknowledged == False,  # noqa: E712
            models.FireAlert.level == "warning",
        )
        .count()
    )
    active = is_fire_alarm_blocking(db)
    message = (
        "ĐANG BÁO CHÁY - Cổng vào/ra đang được giữ mở cho đến khi bảo vệ reset."
        if active
        else "Hệ thống báo cháy đang bình thường."
    )
    return schemas.FireStatus(
        active=active,
        unacknowledged_count=unacknowledged_count,
        critical_count=critical_count,
        warning_count=warning_count,
        message=message,
    )


@router.patch("/api/fire-alerts/{alert_id}/ack", response_model=schemas.FireAlert)
def ack_fire_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(models.FireAlert).get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Khong tim thay canh bao")
    alert.is_acknowledged = True
    db.commit()
    db.refresh(alert)
    return alert




