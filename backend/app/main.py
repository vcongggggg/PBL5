import os
import asyncio
import logging
import time as time_module
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import schemas
from .database import Base, engine
from .core.schema_sync import sync_schema
from .integrations.mqtt_manager import mqtt_manager
from .services.camera_service import camera_manager
from .services.pending_scan_cleanup import cleanup_expired_pending_scans_loop
from .database import SessionLocal
from .core.time_utils import get_vietnam_date, get_vietnam_now
from .core.security import HTTPException, verify_api_key
from .services import ai_service
from .services.config_service import get_system_config_value
from .services.fire_service import is_fire_alarm_blocking, resolve_open_fire_alerts, set_fire_alarm_active
from .state import esp32_ip
from .services.gate_logic import (
    ESP_EVENT_COOLDOWN_SECONDS,
    _last_fire_gate_open_at,
    _esp_event_cooldown,
    _pending_rfid_scans,
    bg_process_esp_event,
    handle_critical_fire_gate_open,
    handle_mqtt_event,
    process_gate_scan,
    process_mqtt_rfid_validation,
)
from .services.parking_service import build_capacity_status, calculate_fee
from .services.pending_scan_cleanup import cleanup_expired_pending_scans_once
from .services.realtime import notify_clients
from .routers import dashboard as dashboard_router
from .routers import fire as fire_router
from .routers import gate as gate_router
from .routers import parking as parking_router
from .routers.gate import _manual_gate_open_until
from .services import gate_logic

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


def _sync_test_facade_dependencies() -> None:
    """Keep legacy tests that patch app.main working after backend split."""
    gate_logic.SessionLocal = SessionLocal
    gate_logic.mqtt_manager = mqtt_manager
    gate_logic.notify_clients = notify_clients
    gate_logic.ESP_EVENT_COOLDOWN_SECONDS = ESP_EVENT_COOLDOWN_SECONDS
    gate_logic._last_fire_gate_open_at = _last_fire_gate_open_at
    gate_logic.time_module = time_module
    gate_logic.asyncio = asyncio

    gate_router.mqtt_manager = mqtt_manager
    gate_router.notify_clients = notify_clients
    gate_router._manual_gate_open_until = _manual_gate_open_until
    parking_router.mqtt_manager = mqtt_manager
    fire_router.mqtt_manager = mqtt_manager
    fire_router.SessionLocal = SessionLocal
    fire_router.notify_clients = notify_clients
    fire_router.resolve_open_fire_alerts = resolve_open_fire_alerts
    fire_router.set_fire_alarm_active = set_fire_alarm_active
    fire_router.handle_critical_fire_gate_open = handle_critical_fire_gate_open


def _pull_test_facade_state() -> None:
    global _last_fire_gate_open_at
    _last_fire_gate_open_at = gate_logic._last_fire_gate_open_at


async def handle_mqtt_event(device_id: str, event_type: str, payload: dict):
    _sync_test_facade_dependencies()
    try:
        return await gate_logic.handle_mqtt_event(device_id, event_type, payload)
    finally:
        _pull_test_facade_state()


async def bg_process_esp_event(direction: str, gate_type: str, device_id: str, scan_token: str):
    _sync_test_facade_dependencies()
    return await gate_logic.bg_process_esp_event(direction, gate_type, device_id, scan_token)


async def process_gate_scan(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await gate_logic.process_gate_scan(*args, **kwargs)


async def process_mqtt_rfid_validation(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await gate_logic.process_mqtt_rfid_validation(*args, **kwargs)


async def force_open_gate(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await gate_router.force_open_gate(*args, **kwargs)


async def gate_sensor_event(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await gate_router.gate_sensor_event(*args, **kwargs)


async def create_fire_alert(*args, **kwargs):
    _sync_test_facade_dependencies()
    try:
        return await fire_router.create_fire_alert(*args, **kwargs)
    finally:
        _pull_test_facade_state()


def get_fire_status(*args, **kwargs):
    _sync_test_facade_dependencies()
    return fire_router.get_fire_status(*args, **kwargs)


async def reset_fire_alarm(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await fire_router.reset_fire_alarm(*args, **kwargs)


def get_dashboard_stats(*args, **kwargs):
    _sync_test_facade_dependencies()
    return dashboard_router.get_dashboard_stats(*args, **kwargs)


async def force_checkout(*args, **kwargs):
    _sync_test_facade_dependencies()
    return await parking_router.force_checkout(*args, **kwargs)


def search_open_parking_sessions(*args, **kwargs):
    _sync_test_facade_dependencies()
    return parking_router.search_open_parking_sessions(*args, **kwargs)
