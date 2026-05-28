import unittest
import os
import sys
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

# Đảm bảo import được backend app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app, get_vietnam_now, handle_mqtt_event, bg_process_esp_event
import app.models as models
import app.main as main_module

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_pbl5.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Mock MQTT Manager để bắt các sự kiện publish lệnh gửi đi
mock_mqtt = MagicMock()
mock_mqtt.is_connected = True

class TestMqttParkingLogic(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        main_module.SessionLocal = TestingSessionLocal
        Base.metadata.create_all(bind=engine)
        main_module.ESP_EVENT_COOLDOWN_SECONDS = 0

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)
        try:
            if os.path.exists("./test_pbl5.db"):
                os.remove("./test_pbl5.db")
        except Exception:
            pass

    def setUp(self):
        # Đảm bảo bind đúng SessionLocal và Mock cho bộ test này (tránh leak giữa các test file của pytest)
        main_module.SessionLocal = TestingSessionLocal
        main_module.mqtt_manager = mock_mqtt
        mock_mqtt.reset_mock()
        mock_mqtt.is_connected = True
        main_module._pending_rfid_scans.clear()

        self.db = TestingSessionLocal()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.commit()

        # Tạo cấu hình hệ thống ban đầu
        self.setup_system_config()

    def tearDown(self):
        self.db.close()

    def setup_system_config(self):
        configs = {
            "api_secret_key": "pbl5_secure_key_12345",
            "plate_confidence_threshold": "0.6",
            "max_parking_slots": "5",
            "rfid_uid_whitelist": "GUEST001,GUEST002,E9B8A7C6",
            "monthly_card_fee": "50000",
            "guest_card_fee_per_hour": "5000"
        }
        for k, v in configs.items():
            db_config = models.SystemConfig(key=k, value=v)
            self.db.add(db_config)
        self.db.commit()

    async def test_01_mqtt_car_detected_creates_processing_scan(self):
        """
        Kiểm tra khi nhận sự kiện car_detected từ MQTT,
        PendingScan được đưa vào DB ở trạng thái PROCESSING ngay lập tức.
        """
        device_id = "esp32-barrier-01"
        payload = {"direction": "in", "gate_id": "gate_in"}

        # Gọi hàm xử lý sự kiện MQTT
        await handle_mqtt_event(device_id, "car_detected", payload)

        # Kiểm tra dữ liệu trong DB ngay lập tức trước khi background task chạy xong
        pending = self.db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.plate_number, "PROCESSING")
        self.assertEqual(pending.device_id, device_id)

    async def test_02_mqtt_rfid_early_swipe_queued(self):
        """
        Kiểm tra tính năng quẹt thẻ sớm:
        1. Xe đến cảm biến -> kích hoạt car_detected -> Trạng thái PROCESSING.
        2. Tài xế quẹt thẻ ngay khi AI đang xử lý (rfid_scan).
        3. Hệ thống không từ chối, lưu UID vào hàng chờ _pending_rfid_scans.
        4. Sau đó AI xử lý xong -> Tự động xác thực và gửi lệnh mở cổng qua MQTT.
        """
        device_id = "esp32-barrier-01"
        
        # 1. Xe kích hoạt cảm biến vào
        await handle_mqtt_event(device_id, "car_detected", {"direction": "in"})
        
        # 2. Quẹt thẻ sớm GUEST001 ngay lập tức khi DB vẫn đang PROCESSING
        await handle_mqtt_event(device_id, "rfid_scan", {"uid": "GUEST001", "direction": "in"})
        
        # Xác nhận UID được lưu vào hàng đợi tạm thời
        self.assertIn("entry", main_module._pending_rfid_scans)
        self.assertEqual(main_module._pending_rfid_scans["entry"][0], "GUEST001")

        # 3. Cho phép event loop chạy để hoàn thành background LPR task và tự kích hoạt RFID validation liên đới
        await asyncio.sleep(0.5)

        # 4. Kỳ vọng hệ thống tự động xác thực xe vào và gửi lệnh mở cổng
        # MQTT Manager phải nhận lệnh publish_open_gate
        main_module.mqtt_manager.publish_open_gate.assert_called_once_with(device_id, "in")
        
        # Hàng đợi tạm thời được dọn dẹp sạch sẽ
        self.assertNotIn("entry", main_module._pending_rfid_scans)
        
        # Pending scan được xóa sau khi mở cổng thành công
        pending_after = self.db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
        self.assertIsNone(pending_after)

    async def test_03_mqtt_fire_alert_logging(self):
        """
        Kiểm tra khi nhận sự kiện báo cháy (fire_alert) qua MQTT,
        Bản ghi báo cháy được lưu vào DB và phát đi WebSocket.
        """
        device_id = "esp32-barrier-01"
        payload = {"sensor_value": 0, "message": "Khói dầy đặc phát hiện"}

        await handle_mqtt_event(device_id, "fire_alert", payload)

        # Kiểm tra DB ghi nhận báo cháy đúng schema
        alert = self.db.query(models.FireAlert).filter(models.FireAlert.sensor_id == device_id).first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.message, "Khói dầy đặc phát hiện")
        self.assertEqual(alert.level, "critical")

if __name__ == "__main__":
    unittest.main()
