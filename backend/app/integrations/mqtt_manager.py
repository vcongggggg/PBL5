import json
import logging
import asyncio
import time
import paho.mqtt.client as mqtt
from typing import Optional

logger = logging.getLogger("uvicorn")

class MQTTManager:
    def __init__(self):
        self.client: Optional[mqtt.Client] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.broker_host: str = "broker.hivemq.com"  # Broker mặc định công cộng để tiện test
        self.broker_port: int = 1883
        self.client_id: str = "fastapi-backend-parking"
        self.is_connected: bool = False
        self.latest_rfid_scan: Optional[dict] = None
        self.rfid_registration_mode: bool = False
        self.rfid_registration_mode_until: float = 0.0
        self.latest_registration_rfid: Optional[dict] = None

    def init_app(self, loop: asyncio.AbstractEventLoop, broker_host: str = "broker.hivemq.com", broker_port: int = 1883):
        self.loop = loop
        self.broker_host = broker_host
        self.broker_port = broker_port
        
        self.client = mqtt.Client(client_id=self.client_id)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        
        logger.info(f"MQTT init: broker={self.broker_host}:{self.broker_port}")

    def start(self):
        if self.client:
            try:
                self.client.connect(self.broker_host, self.broker_port, keepalive=60)
                self.client.loop_start()
            except Exception as e:
                logger.error(f"Failed to connect to MQTT Broker: {e}")

    def stop(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.is_connected = False
            logger.info("MQTT client disconnected.")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            logger.info("Successfully connected to MQTT Broker!")
            # Đăng ký nhận tin nhắn từ tất cả các thiết bị ESP32 gửi lên
            self.client.subscribe("parking/device/+/event/car_detected")
            self.client.subscribe("parking/device/+/event/rfid_scan")
            self.client.subscribe("parking/device/+/event/fire_alert")
            self.client.subscribe("parking/device/+/event/fire_telemetry")
            logger.info("Subscribed to MQTT topics.")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def on_disconnect(self, client, userdata, rc):
        self.is_connected = False
        logger.warning(f"Disconnected from MQTT Broker with code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload_str = msg.payload.decode('utf-8')
            payload = json.loads(payload_str)
            if "fire_telemetry" not in topic:
                logger.info(f"MQTT received: {topic} -> {payload_str}")

            parts = topic.split('/')
            if len(parts) >= 5:
                device_id = parts[2]
                event_type = parts[4]
                if event_type == "rfid_scan":
                    uid = str(payload.get("uid") or "").strip().upper().replace(" ", "").replace(":", "")
                    if uid:
                        scan_data = {
                            "uid": uid,
                            "device_id": device_id,
                            "direction": payload.get("direction"),
                            "gate_id": payload.get("gate_id"),
                            "received_at_ts": time.time(),
                        }
                        self.latest_rfid_scan = scan_data
                        if self.is_rfid_registration_mode_active():
                            self.latest_registration_rfid = scan_data
                            if self.loop:
                                asyncio.run_coroutine_threadsafe(
                                    self.notify_rfid_registration_scan(scan_data),
                                    self.loop,
                                )
                            logger.info(f"RFID registration mode captured UID: {uid}")
                            return

                # Đẩy luồng bất đồng bộ sang event loop của FastAPI để chạy xử lý logic an toàn
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self.handle_event(device_id, event_type, payload),
                        self.loop
                    )
        except Exception as e:
            logger.error(f"Error handling MQTT message: {e}")

    async def notify_rfid_registration_scan(self, scan_data: dict):
        from ..services.realtime import notify_clients
        await notify_clients("rfid_registration_scan", scan_data)

    def set_rfid_registration_mode(self, enabled: bool):
        self.rfid_registration_mode = bool(enabled)
        self.rfid_registration_mode_until = time.time() + 120 if enabled else 0.0
        if enabled:
            self.latest_registration_rfid = None

    def is_rfid_registration_mode_active(self) -> bool:
        if not self.rfid_registration_mode:
            return False
        if time.time() <= self.rfid_registration_mode_until:
            return True
        self.rfid_registration_mode = False
        self.rfid_registration_mode_until = 0.0
        return False

    def get_latest_registration_rfid(self) -> Optional[dict]:
        return self.latest_registration_rfid.copy() if self.latest_registration_rfid else None

    async def handle_event(self, device_id: str, event_type: str, payload: dict):
        # Tránh import vòng (circular imports)
        from ..main import handle_mqtt_event
        try:
            await handle_mqtt_event(device_id, event_type, payload)
        except Exception as e:
            logger.error(f"Error running handle_mqtt_event for device={device_id}, event={event_type}: {e}")

    def publish_open_gate(self, device_id: str, gate: str):
        if self.client and self.is_connected:
            topic = f"parking/device/{device_id}/command/open_gate"
            payload = json.dumps({"gate": gate})
            self.client.publish(topic, payload, qos=1)
            logger.info(f"MQTT published open command: {topic} -> {payload}")
        else:
            logger.warning(f"Cannot publish open command to {device_id}: MQTT not connected.")

    def publish_reset_fire(self, device_id: str):
        if self.client and self.is_connected:
            topic = f"parking/device/{device_id}/command/reset_fire"
            payload = json.dumps({})
            self.client.publish(topic, payload, qos=1)
            logger.info(f"MQTT published reset fire command to {device_id}")
        else:
            logger.warning(f"Cannot publish reset fire to {device_id}: MQTT not connected.")

mqtt_manager = MQTTManager()
