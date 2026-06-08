from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.realtime import manager, notify_clients

router = APIRouter()
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


