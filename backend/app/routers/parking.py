from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas
from ..database import get_db
from ..core.string_utils import levenshtein_distance
from ..services.parking_service import resolve_session_ticket_type, calculate_fee, normalize_manual_reason, get_rfid_card, create_manual_gate_log
from ..services.image_storage import image_url_from_path
from ..services import ai_service
from ..core.security import verify_api_key
from ..core.time_utils import get_vietnam_now
from ..integrations.mqtt_manager import mqtt_manager
from .. import state
from ..services.realtime import notify_clients
from ..services.parking_service import get_lost_rfid_compensation_fee

from ..services.gate_logic import process_gate_scan


router = APIRouter()


@router.get("/api/parking/open-sessions/search")
def search_open_parking_sessions(q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    query_norm = ai_service.normalize_plate(q or "")
    safe_limit = max(1, min(int(limit or 8), 20))
    sessions = (
        db.query(models.ParkingSession)
        .filter(models.ParkingSession.time_out.is_(None))
        .order_by(models.ParkingSession.time_in.desc(), models.ParkingSession.id.desc())
        .limit(200)
        .all()
    )

    results = []
    for session in sessions:
        plate_norm = ai_service.normalize_plate(session.plate_number or "")
        if query_norm:
            distance = levenshtein_distance(query_norm, plate_norm)
            contains = query_norm in plate_norm
            prefix = plate_norm.startswith(query_norm)
            if not contains and not prefix and distance > 3:
                continue
        else:
            distance = 0
            contains = False
            prefix = False

        if prefix:
            score = 0
        elif contains:
            score = 1
        else:
            score = 2 + distance

        results.append({
            "session_id": session.id,
            "plate_number": session.plate_number,
            "rfid_tag": session.rfid_tag,
            "time_in": session.time_in,
            "ticket_type": resolve_session_ticket_type(db, session),
            "image_url": image_url_from_path(session.image_path),
            "distance": distance,
            "score": score,
        })

    results.sort(key=lambda item: (item["score"], item["distance"], item["time_in"]), reverse=False)
    return results[:safe_limit]


@router.get("/api/parking-history", response_model=List[schemas.ParkingHistoryItem])
def list_parking_history(limit: int = 100, db: Session = Depends(get_db)):
    sessions = (
        db.query(models.ParkingSession)
        .order_by(models.ParkingSession.time_in.desc(), models.ParkingSession.id.desc())
        .limit(limit)
        .all()
    )

    items: List[schemas.ParkingHistoryItem] = []
    for session in sessions:
        duration_minutes = None
        if session.time_out:
            duration_minutes = int((session.time_out - session.time_in).total_seconds() // 60)

        items.append(
            schemas.ParkingHistoryItem(
                session_id=session.id,
                plate_number=session.plate_number,
                ticket_type=resolve_session_ticket_type(db, session),
                gate_type=session.gate_type,
                trigger_type=session.trigger_type,
                time_in=session.time_in,
                time_out=session.time_out,
                duration_minutes=duration_minutes,
                fee=session.fee or 0,
                match_status=session.match_status,
            )
        )
    return items


@router.get("/api/parking/export")
def export_parking_history(db: Session = Depends(get_db)):
    import csv
    import io
    
    sessions = (
        db.query(models.ParkingSession)
        .order_by(models.ParkingSession.time_in.desc(), models.ParkingSession.id.desc())
        .all()
    )

    def generate():
        # Trả về UTF-8 BOM để Excel hiển thị đúng tiếng Việt
        yield "\ufeff".encode('utf-8')
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Tiêu đề cột
        writer.writerow([
            "Mã phiên", "Biển số xe", "Loại vé", "Cổng", 
            "Cách thức", "Thời gian vào", "Thời gian ra", 
            "Thời gian đỗ (phút)", "Phí gửi (VND)", "Trạng thái"
        ])
        yield output.getvalue().encode('utf-8')
        output.seek(0)
        output.truncate(0)

        for session in sessions:
            duration = ""
            if session.time_out:
                duration = str(int((session.time_out - session.time_in).total_seconds() // 60))
            
            time_in_str = session.time_in.strftime("%Y-%m-%d %H:%M:%S") if session.time_in else ""
            time_out_str = session.time_out.strftime("%Y-%m-%d %H:%M:%S") if session.time_out else ""
            ticket_type = resolve_session_ticket_type(db, session)
            
            # Map values to Vietnamese for friendly CSV report
            gate = "Cổng vào" if session.gate_type == "entry" else "Cổng ra"
            trigger = "Tự động" if session.trigger_type == "sensor" else ("Thẻ RFID" if session.trigger_type == "rfid" else "Thủ công")
            match_status_vn = "Hợp lệ" if session.match_status == "matched" else (
                "Fuzzy (Nhận diện mờ)" if session.match_status == "fuzzy_matched" else (
                    "Đang chờ" if session.match_status == "pending" else (
                        "Từ chối/Bị hủy" if session.match_status == "ignored" else session.match_status or ""
                    )
                )
            )

            writer.writerow([
                session.id,
                session.plate_number,
                "Vé tháng" if ticket_type == "monthly" else "Vé lượt",
                gate,
                trigger,
                time_in_str,
                time_out_str,
                duration,
                int(session.fee or 0),
                match_status_vn
            ])
            yield output.getvalue().encode('utf-8')
            output.seek(0)
            output.truncate(0)

    headers = {
        'Content-Disposition': 'attachment; filename="parking_history.csv"',
        'Content-Type': 'text/csv; charset=utf-8',
    }
    return StreamingResponse(generate(), headers=headers)




# ============ PARKING CHECK-OUT (legacy) ============
@router.post("/api/parking/check-out", response_model=schemas.ParkingCheckoutResponse)
def parking_check_out(payload: schemas.ParkingCheckoutRequest, db: Session = Depends(get_db)):
    now = get_vietnam_now()

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
            detail="Khong tim thay phien gui dang mo cho bien so nay",
        )

    duration_minutes, fee = calculate_fee(now, session, db)
    session.time_out = now
    session.fee = fee
    session.gate_type = "exit"
    session.plate_out = payload.plate_number
    session.match_status = "matched"

    db.commit()
    db.refresh(session)

    return schemas.ParkingCheckoutResponse(
        session=session,
        duration_minutes=duration_minutes,
    )


# ============ FORCE CHECKOUT (Mất thẻ / Xe kẹt) ============
@router.post("/api/parking/force-checkout")
async def force_checkout(
    plate_number: Optional[str] = Form(None),
    rfid_tag: Optional[str] = Form(None),
    reason: str = Form("lost_card"),
    open_gate: bool = Form(True),
    operator: str = Form("operator"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Bảo vệ tìm xe theo biển số, tính phí thủ công, kết thúc session.
    Tùy chọn mở cổng ra cho xe.
    """
    reason = normalize_manual_reason(reason)
    operator = operator if isinstance(operator, str) else "operator"
    plate_norm = ai_service.normalize_plate(plate_number or "")
    rfid_norm = (rfid_tag if isinstance(rfid_tag, str) else "").strip().upper().replace(" ", "").replace(":", "")
    now = get_vietnam_now()

    session = None
    if rfid_norm:
        session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.rfid_tag == rfid_norm,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )
    if not session and plate_norm:
        session = (
            db.query(models.ParkingSession)
            .filter(
                models.ParkingSession.plate_number == plate_norm,
                models.ParkingSession.time_out.is_(None),
            )
            .order_by(models.ParkingSession.time_in.desc())
            .first()
        )
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Không tìm thấy phiên gửi xe đang mở cho biển số {plate_norm}",
        )

    ticket_type = resolve_session_ticket_type(db, session)
    duration_minutes, parking_fee = calculate_fee(now, session, db, ticket_type=ticket_type)
    compensation_fee = get_lost_rfid_compensation_fee(db) if reason == "lost_card" else 0.0
    fee = parking_fee + compensation_fee

    session.time_out = now
    session.fee = fee
    session.plate_out = plate_norm or session.plate_number
    session.match_status = "manual"

    # Cập nhật trạng thái thẻ RFID thành "available" và vô hiệu hóa nếu báo mất thẻ khi force checkout
    if session.rfid_tag:
        rfid_card_to_release = get_rfid_card(db, session.rfid_tag)
        if rfid_card_to_release:
            rfid_card_to_release.status = "available"
            if reason == "lost_card":
                rfid_card_to_release.is_active = False

    create_manual_gate_log(
        db,
        "exit",
        "force_checkout",
        reason=reason,
        operator=operator,
        source="web",
    )

    # Clear pending scan of exit gate
    try:
        db.query(models.PendingScan).filter(models.PendingScan.gate_type == "exit").delete()
    except Exception as e:
        logger.error(f"Error clearing pending scan on force checkout: {e}")

    db.commit()
    db.refresh(session)

    # Mở cổng ra nếu cần
    gate_opened = False
    if open_gate:
        
        if mqtt_manager.is_connected:
            mqtt_manager.publish_open_gate("esp32-barrier-01", "out")
            gate_opened = True
        elif state.esp32_ip:
            import urllib.request
            import urllib.error
            from fastapi.concurrency import run_in_threadpool

            def send_open():
                try:
                    req = urllib.request.Request(
                        f"http://{state.esp32_ip}/open-gate?gate=out", method="GET"
                    )
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        return resp.getcode() == 200
                except Exception:
                    return False

            gate_opened = await run_in_threadpool(send_open)

    await notify_clients("parking_update", {
        "action": "force_checkout",
        "gate_type": "exit",
        "plate": session.plate_number,
        "plate_out": session.plate_out,
        "rfid_tag": rfid_norm or session.rfid_tag,
        "fee": fee,
        "parking_fee": parking_fee,
        "compensation_fee": compensation_fee,
        "reason": reason,
        "session_id": session.id,
    })

    fee_fmt = f"{int(fee):,}đ" if fee > 0 else "Miễn phí (vé tháng)"
    return {
        "status": "ok",
        "session_id": session.id,
        "plate_number": session.plate_number,
        "plate_out": session.plate_out,
        "rfid_tag": rfid_norm or session.rfid_tag,
        "duration_minutes": duration_minutes,
        "fee": fee,
        "parking_fee": parking_fee,
        "compensation_fee": compensation_fee,
        "fee_display": fee_fmt,
        "gate_opened": gate_opened,
        "message": f"Đã checkout thủ công xe {plate_norm}. Phí: {fee_fmt}. Thời gian gửi: {duration_minutes} phút.",
    }





@router.post("/api/parking/check-in", response_model=schemas.ParkingCheckinResponse)
async def parking_check_in(
    file: UploadFile = File(...),
    direction: str = Form("in"),
    device_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image")

    gate_type = "entry" if direction == "in" else "exit"
    scan_result = await process_gate_scan(
        db=db,
        image_bytes=image_bytes,
        filename=file.filename,
        gate_type=gate_type,
        trigger_type="manual",
        source_id=device_id,
        rfid_tag=None,
    )

    return schemas.ParkingCheckinResponse(
        action=scan_result.action,
        plate=scan_result.recognized_plate,
        confidence=scan_result.confidence,
        valid_plate=scan_result.valid_plate,
        vehicle_type="guest",
        message=scan_result.message,
        session_id=scan_result.session_id,
    )



