import os
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .core.schema_sync import sync_schema
from .integrations.mqtt_manager import mqtt_manager
from .services.camera_service import camera_manager
from .services.pending_scan_cleanup import cleanup_expired_pending_scans_loop

logger = logging.getLogger("uvicorn")

# Initialize Database
sync_schema(engine)
Base.metadata.create_all(bind=engine)

# Initialize FastAPI
app = FastAPI(title="PBL5 Smart Parking API")

# Setup static files directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Add Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup and Shutdown Events
@app.on_event("startup")
def startup_event():
    # Khởi tạo MQTT client chạy ngầm (nếu có mqtt_manager)
    loop = asyncio.get_running_loop()
    mqtt_host = os.environ.get("MQTT_BROKER", "localhost")
    try:
        mqtt_port = int(os.environ.get("MQTT_PORT", 1883))
    except ValueError:
        mqtt_port = 1883
        
    mqtt_manager.init_app(loop, broker_host=mqtt_host, broker_port=mqtt_port)
    mqtt_manager.start()

    # Kích hoạt task dọn dẹp chạy ngầm định kỳ
    asyncio.create_task(cleanup_expired_pending_scans_loop())

@app.on_event("shutdown")
def shutdown_event():
    mqtt_manager.stop()
    camera_manager.is_running = False
    camera_manager.release_all()

# Include Routers
from .routers import ws, gate, esp, camera, ai, admin, fire, parking, dashboard
app.include_router(ws.router)
app.include_router(gate.router)
app.include_router(esp.router)
app.include_router(camera.router)
app.include_router(ai.router)
app.include_router(admin.router)
app.include_router(fire.router)
app.include_router(parking.router)
app.include_router(dashboard.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
