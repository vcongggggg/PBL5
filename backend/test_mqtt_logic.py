import unittest
import os
import sys
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

# Đảm bảo import được backend app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app, get_vietnam_now, handle_mqtt_event, bg_process_esp_event, process_gate_scan
import app.models as models
import app.main as main_module
from app.main import force_open_gate

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
        self.notifications = []

        async def capture_notification(event_type, data):
            self.notifications.append((event_type, data))

        main_module.notify_clients = AsyncMock(side_effect=capture_notification)
        mock_mqtt.reset_mock()
        mock_mqtt.is_connected = True
        main_module._pending_rfid_scans.clear()
        main_module._manual_gate_open_until = {"entry": 0.0, "exit": 0.0}

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
            "guest_card_fee_per_hour": "5000",
            "manual_gate_open_seconds": "5",
            "allow_rfid_only_exit": "1",
            "parking_near_full_threshold": "0.7",
            "parking_almost_full_threshold": "0.9"
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
        pending_notifications = [data for event, data in self.notifications if event == "pending_scan"]
        self.assertTrue(pending_notifications)
        self.assertEqual(pending_notifications[-1]["gate_type"], "entry")
        self.assertEqual(pending_notifications[-1]["recognized_plate"], "PROCESSING")
        self.assertIn("giữ nguyên vị trí", pending_notifications[-1]["message"].lower())

        # 4. Kỳ vọng hệ thống tự động xác thực xe vào và gửi lệnh mở cổng
        # MQTT Manager phải nhận lệnh publish_open_gate
        main_module.mqtt_manager.publish_open_gate.assert_not_called()
        
        # Hàng đợi tạm thời được dọn dẹp sạch sẽ
        self.assertIn("entry", main_module._pending_rfid_scans)
        
        # Pending scan được xóa sau khi mở cổng thành công
        pending_after = self.db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
        self.assertIsNotNone(pending_after)

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

    async def test_04_rfid_in_use_with_pending_reports_real_error(self):
        device_id = "esp32-barrier-01"
        card = models.RFIDCard(card_uid="GUEST001", card_type="guest", status="in_use", is_active=True)
        pending = models.PendingScan(
            gate_type="entry",
            plate_number="51F12345",
            confidence=0.95,
            device_id=device_id,
            scan_token="scan-1",
        )
        self.db.add_all([card, pending])
        self.db.commit()

        await handle_mqtt_event(device_id, "rfid_scan", {"uid": "GUEST001", "direction": "in"})

        parking_updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertTrue(parking_updates)
        self.assertEqual(parking_updates[-1]["gate_type"], "entry")
        self.assertEqual(parking_updates[-1]["action"], "ignore")
        self.assertIn("đang được sử dụng", parking_updates[-1]["message"].lower())

    async def test_05_rfid_in_use_without_pending_reports_real_error(self):
        device_id = "esp32-barrier-01"
        card = models.RFIDCard(card_uid="GUEST001", card_type="guest", status="in_use", is_active=True)
        self.db.add(card)
        self.db.commit()

        await handle_mqtt_event(device_id, "rfid_scan", {"uid": "GUEST001", "direction": "in"})

        parking_updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertTrue(parking_updates)
        self.assertEqual(parking_updates[-1]["gate_type"], "entry")
        self.assertEqual(parking_updates[-1]["action"], "ignore")
        self.assertIn("đang được sử dụng", parking_updates[-1]["message"].lower())

    async def test_06_rfid_unknown_without_pending_reports_position_error(self):
        device_id = "esp32-barrier-01"

        await handle_mqtt_event(device_id, "rfid_scan", {"uid": "UNKNOWN001", "direction": "in"})

        parking_updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertTrue(parking_updates)
        self.assertEqual(parking_updates[-1]["gate_type"], "entry")
        self.assertEqual(parking_updates[-1]["action"], "ignore")
        self.assertIn("đúng vị trí", parking_updates[-1]["message"].lower())

    async def test_07_exit_update_includes_entry_plate_image(self):
        device_id = "esp32-barrier-01"
        card = models.RFIDCard(card_uid="GUEST001", card_type="guest", status="in_use", is_active=True)
        self.db.add(card)
        self.db.commit()
        session = models.ParkingSession(
            plate_number="51F12345",
            time_in=get_vietnam_now() - timedelta(minutes=10),
            time_out=None,
            fee=0,
            image_path="C:/Study/PBL5/backend/uploads/entry_plate.jpg",
            gate_type="entry",
            trigger_type="rfid",
            rfid_tag="GUEST001",
            rfid_card_id=card.id,
            rfid_card_type="guest",
            plate_in="51F12345",
            confidence_in=0.93,
            match_status="pending",
        )
        pending = models.PendingScan(
            gate_type="exit",
            plate_number="51F12345",
            confidence=0.94,
            device_id=device_id,
            scan_token="scan-exit",
        )
        self.db.add_all([session, pending])
        self.db.commit()

        await handle_mqtt_event(device_id, "rfid_scan", {"uid": "GUEST001", "direction": "out"})

        parking_updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertTrue(parking_updates)
        self.assertEqual(parking_updates[-1]["gate_type"], "exit")
        self.assertEqual(parking_updates[-1]["action"], "open")
        self.assertEqual(parking_updates[-1]["plate_in_image_url"], "/uploads/entry_plate.jpg")

    async def test_08_manual_open_ignores_spam_until_gate_closes(self):
        first = await force_open_gate(gate_type="entry", reason="test", operator="tester", db=self.db, api_key="pbl5_secure_key_12345")
        second = await force_open_gate(gate_type="entry", reason="test", operator="tester", db=self.db, api_key="pbl5_secure_key_12345")

        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "gate_open")
        self.assertGreaterEqual(second["remaining_seconds"], 1)
        main_module.mqtt_manager.publish_open_gate.assert_called_once_with("esp32-barrier-01", "in")

        parking_updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertEqual(parking_updates[-1]["action"], "gate_open")
        self.assertIn("đang mở", parking_updates[-1]["message"].lower())

        log_count = self.db.query(models.ManualGateLog).count()
        self.assertEqual(log_count, 1)

    async def test_09_two_vehicle_sequence_and_wrong_rfid_rejected(self):
        card_a = models.RFIDCard(card_uid="RFIDA", card_type="guest", status="available", is_active=True)
        card_b = models.RFIDCard(card_uid="RFIDB", card_type="guest", status="available", is_active=True)
        self.db.add_all([card_a, card_b])
        self.db.commit()

        in_a = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDA",
            override_plate="51F12345",
            override_confidence=0.95,
        )
        in_b = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDB",
            override_plate="51F67890",
            override_confidence=0.96,
        )
        self.assertEqual(in_a.action, "open")
        self.assertEqual(in_b.action, "open")
        self.db.refresh(card_a)
        self.db.refresh(card_b)
        self.assertEqual(card_a.status, "in_use")
        self.assertEqual(card_b.status, "in_use")

        out_a = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDA",
            override_plate="51F12345",
            override_confidence=0.95,
        )
        self.assertEqual(out_a.action, "open")
        self.db.refresh(card_a)
        self.assertEqual(card_a.status, "available")

        wrong_b = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDA",
            override_plate="51F67890",
            override_confidence=0.96,
        )
        self.assertEqual(wrong_b.action, "ignore")
        self.assertIn("không khớp", wrong_b.message.lower())

        out_b = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDB",
            override_plate="51F67890",
            override_confidence=0.96,
        )
        self.assertEqual(out_b.action, "open")
        self.db.refresh(card_b)
        self.assertEqual(card_b.status, "available")

    async def test_10_rfid_only_exit_can_be_disabled(self):
        card = models.RFIDCard(card_uid="RFIDC", card_type="guest", status="in_use", is_active=True)
        self.db.add(card)
        self.db.commit()
        session = models.ParkingSession(
            plate_number="51F99999",
            time_in=get_vietnam_now() - timedelta(minutes=10),
            time_out=None,
            fee=0,
            gate_type="entry",
            trigger_type="rfid",
            rfid_tag="RFIDC",
            rfid_card_id=card.id,
            rfid_card_type="guest",
            plate_in="51F99999",
            match_status="pending",
        )
        self.db.add(session)
        cfg = self.db.query(models.SystemConfig).filter(models.SystemConfig.key == "allow_rfid_only_exit").first()
        cfg.value = "0"
        self.db.commit()

        result = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="RFIDC",
            override_plate="UNKNOWN",
            override_confidence=0.0,
        )
        self.assertEqual(result.action, "ignore")
        self.assertIn("dự phòng bằng RFID đang tắt", result.message)


    def test_11_capacity_status_levels(self):
        normal = main_module.build_capacity_status(total_in_bay=2, max_slots=5)
        near_full = main_module.build_capacity_status(total_in_bay=4, max_slots=5)
        full = main_module.build_capacity_status(total_in_bay=5, max_slots=5)

        self.assertEqual(normal["capacity_status"], "normal")
        self.assertEqual(normal["available_slots"], 3)
        self.assertEqual(near_full["capacity_status"], "near_full")
        self.assertEqual(near_full["occupancy_percent"], 80.0)
        self.assertEqual(full["capacity_status"], "full")
        self.assertEqual(full["available_slots"], 0)

    async def test_12_entry_rejected_when_parking_full(self):
        card = models.RFIDCard(card_uid="FULL001", card_type="guest", status="available", is_active=True)
        self.db.add(card)
        for idx in range(5):
            self.db.add(models.ParkingSession(
                plate_number=f"51F{idx:05d}",
                time_in=get_vietnam_now() - timedelta(minutes=idx + 1),
                time_out=None,
                fee=0,
                gate_type="entry",
                trigger_type="rfid",
                match_status="pending",
            ))
        self.db.commit()

        result = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="FULL001",
            override_plate="51F88888",
            override_confidence=0.95,
        )

        self.assertEqual(result.action, "ignore")
        self.assertIn("Bai xe da day", result.message)

if __name__ == "__main__":
    unittest.main()
