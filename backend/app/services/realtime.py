import json
from typing import List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass

    async def broadcast(self, message: dict):
        from fastapi.encoders import jsonable_encoder

        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(jsonable_encoder(message)))
            except Exception:
                pass


manager = ConnectionManager()


async def notify_clients(event_type: str, data: dict):
    from fastapi.encoders import jsonable_encoder

    await manager.broadcast({"event": event_type, "data": jsonable_encoder(data)})
