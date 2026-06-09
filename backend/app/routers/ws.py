import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from ..services.realtime import manager

router = APIRouter()

HEARTBEAT_INTERVAL = 30  # Gửi ping mỗi 30 giây
HEARTBEAT_TIMEOUT = 10   # Chờ pong tối đa 10 giây


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                # Đợi message từ client với timeout = HEARTBEAT_INTERVAL
                # Nếu không nhận gì trong 30s → gửi ping kiểm tra
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                # Không nhận message nào → gửi ping để kiểm tra client còn sống không
                try:
                    await asyncio.wait_for(
                        websocket.send_text('{"event":"ping"}'),
                        timeout=HEARTBEAT_TIMEOUT,
                    )
                except (asyncio.TimeoutError, Exception):
                    # Client không phản hồi hoặc lỗi gửi → zombie connection → ngắt
                    break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)
        # Đảm bảo đóng kết nối nếu chưa đóng
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
