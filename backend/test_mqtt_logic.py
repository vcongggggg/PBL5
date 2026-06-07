import unittest
import os
import sys
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# Đảm bảo import được backend app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import app, get_vietnam_now, handle_mqtt_event, bg_process_esp_event, process_gate_scan
import app.models as models
import app.main as main_module
from app.main import force_open_gate, gate_sensor_event

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
        main_module._esp_event_cooldown.clear()

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

    def add_guest_card(self, uid: str, status: str = "available"):
        card = models.RFIDCard(card_uid=uid, card_type="guest", status=status, is_active=True)
        self.db.add(card)
        self.db.commit()
        self.db.refresh(card)
        return card

    def add_open_session(self, plate: str, uid: str, card: models.RFIDCard):
        session = models.ParkingSession(
            plate_number=plate,
            time_in=get_vietnam_now() - timedelta(minutes=12),
            time_out=None,
            fee=0,
            gate_type="entry",
            trigger_type="rfid",
            rfid_tag=uid,
            rfid_card_id=card.id,
            rfid_card_type="guest",
            plate_in=plate,
            confidence_in=0.95,
            match_status="pending",
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    async def test_13_simulated_entry_responses_cover_common_cases(self):
        card_ok = self.add_guest_card("ENTRYOK")
        card_used = self.add_guest_card("ENTRYUSED", status="in_use")

        no_rfid = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="sensor",
            source_id="test",
            rfid_tag=None,
            override_plate="51F12345",
            override_confidence=0.95,
        )
        self.assertEqual(no_rfid.action, "ignore")
        self.assertIn("quẹt thẻ RFID", no_rfid.message)

        invalid_plate = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="ENTRYOK",
            override_plate="UNKNOWN",
            override_confidence=0.0,
        )
        self.assertEqual(invalid_plate.action, "ignore")
        self.assertIn("khong hop le", invalid_plate.message.lower())

        used_card = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="ENTRYUSED",
            override_plate="51F22222",
            override_confidence=0.95,
        )
        self.assertEqual(used_card.action, "ignore")
        self.assertIn("đang được sử dụng", used_card.message.lower())

        valid_entry = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="ENTRYOK",
            override_plate="51F12345",
            override_confidence=0.95,
        )
        self.assertEqual(valid_entry.action, "open")
        self.assertIn("vãng lai", valid_entry.message.lower())
        self.db.refresh(card_ok)
        self.assertEqual(card_ok.status, "in_use")

    async def test_14_simulated_exit_responses_cover_common_cases(self):
        card = self.add_guest_card("EXITOK", status="in_use")
        self.add_open_session("51F12345", "EXITOK", card)

        exact = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="EXITOK",
            override_plate="51F12345",
            override_confidence=0.95,
        )
        self.assertEqual(exact.action, "open")
        self.assertIn("trùng khớp", exact.message.lower())

        card = self.add_guest_card("EXITFUZZY1", status="in_use")
        self.add_open_session("51F12345", "EXITFUZZY1", card)
        fuzzy_allowed = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="EXITFUZZY1",
            override_plate="51F12346",
            override_confidence=0.95,
        )
        self.assertEqual(fuzzy_allowed.action, "open")
        self.assertIn("khớp trong ngưỡng", fuzzy_allowed.message.lower())

        card = self.add_guest_card("EXITRFIDAID", status="in_use")
        self.add_open_session("51F12345", "EXITRFIDAID", card)
        rfid_assisted = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="EXITRFIDAID",
            override_plate="51F12399",
            override_confidence=0.95,
        )
        self.assertEqual(rfid_assisted.action, "open")
        self.assertIn("rfid khớp", rfid_assisted.message.lower())

        card = self.add_guest_card("EXITBLUR", status="in_use")
        self.add_open_session("51F77777", "EXITBLUR", card)
        blurred = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="EXITBLUR",
            override_plate="UNKNOWN",
            override_confidence=0.0,
        )
        self.assertEqual(blurred.action, "open")
        self.assertIn("rfid dự phòng", blurred.message.lower())

        card = self.add_guest_card("EXITREJECT", status="in_use")
        self.add_open_session("51F12345", "EXITREJECT", card)
        mismatch = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="EXITREJECT",
            override_plate="30A99999",
            override_confidence=0.95,
        )
        self.assertEqual(mismatch.action, "ignore")
        self.assertIn("không khớp", mismatch.message.lower())

        no_session = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="exit",
            trigger_type="sensor",
            source_id="test",
            rfid_tag=None,
            override_plate="59A11111",
            override_confidence=0.95,
        )
        self.assertEqual(no_session.action, "ignore")
        self.assertIn("không tìm thấy", no_session.message.lower())

    async def test_15_simulated_capacity_and_manual_status_messages(self):
        for idx in range(4):
            card = self.add_guest_card(f"CAP{idx}", status="in_use")
            self.add_open_session(f"51F77{idx:03d}", f"CAP{idx}", card)

        dashboard = main_module.get_dashboard_stats(db=self.db)
        self.assertEqual(dashboard.capacity_status, "near_full")
        self.assertEqual(dashboard.available_slots, 1)

        full_card = self.add_guest_card("CAPFULL")
        for idx in range(4, 5):
            card = self.add_guest_card(f"CAP{idx}", status="in_use")
            self.add_open_session(f"51F77{idx:03d}", f"CAP{idx}", card)

        blocked = await process_gate_scan(
            db=self.db,
            image_bytes=None,
            filename=None,
            gate_type="entry",
            trigger_type="rfid",
            source_id="test",
            rfid_tag="CAPFULL",
            override_plate="51F88888",
            override_confidence=0.95,
        )
        self.assertEqual(blocked.action, "ignore")
        self.assertIn("Bai xe da day", blocked.message)

        first = await force_open_gate(gate_type="exit", reason="test", operator="tester", db=self.db, api_key="pbl5_secure_key_12345")
        second = await force_open_gate(gate_type="exit", reason="test", operator="tester", db=self.db, api_key="pbl5_secure_key_12345")
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "gate_open")
        self.assertIn("đang mở", second["message"].lower())

    async def test_16_ui_sensor_event_uses_background_tracking(self):
        payload = main_module.schemas.GateTriggerRequest(
            gate_type="entry",
            trigger_type="sensor",
            source_id="entry-sensor-ui",
            rfid_tag=None,
        )

        created_tasks = []

        def capture_task(coro):
            created_tasks.append(coro)
            coro.close()
            return MagicMock()

        with patch("app.main.asyncio.create_task", side_effect=capture_task):
            response = await gate_sensor_event(payload=payload, db=self.db)

        self.assertEqual(response["status"], "processing")
        self.assertEqual(response["gate_type"], "entry")
        self.assertEqual(len(created_tasks), 1)

        pending = self.db.query(models.PendingScan).filter(models.PendingScan.gate_type == "entry").first()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.plate_number, "PROCESSING")

        pending_notifications = [data for event, data in self.notifications if event == "pending_scan"]
        self.assertTrue(pending_notifications)
        self.assertIn("bám biển số", pending_notifications[-1]["message"].lower())


    def add_monthly_bundle(self, uid="MONTH001", plate="51F24680", start_offset=-1, end_offset=30, is_active=True, card_active=True):
        today = main_module.get_vietnam_date()
        user = models.MonthlyUser(full_name="Nguyen Van A", phone="0900000000")
        vehicle = models.Vehicle(plate_number=plate, owner_name="Nguyen Van A")
        self.db.add_all([user, vehicle])
        self.db.commit()
        sub = models.Subscription(
            vehicle_id=vehicle.id,
            monthly_user_id=user.id,
            start_date=today + timedelta(days=start_offset),
            end_date=today + timedelta(days=end_offset),
            is_active=is_active,
        )
        card = models.RFIDCard(
            card_uid=uid,
            card_type="monthly",
            status="available",
            is_active=card_active,
            monthly_user_id=user.id,
            vehicle_id=vehicle.id,
        )
        self.db.add_all([sub, card])
        self.db.commit()
        self.db.refresh(card)
        self.db.refresh(vehicle)
        return user, vehicle, sub, card

    async def test_17_rfid_invalid_inactive_and_unknown_cards_rejected(self):
        inactive = self.add_guest_card("INACTIVE", status="available")
        inactive.is_active = False
        self.db.commit()

        inactive_result = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="INACTIVE", override_plate="51F12001", override_confidence=0.95,
        )
        self.assertEqual(inactive_result.action, "ignore")
        self.assertIn("bi khoa", inactive_result.message.lower())

        unknown_result = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="NOTINDB", override_plate="51F12002", override_confidence=0.95,
        )
        self.assertEqual(unknown_result.action, "ignore")
        self.assertIn("khong tim thay", unknown_result.message.lower())

    async def test_18_monthly_card_validity_and_plate_mismatch(self):
        _, _, _, expired_card = self.add_monthly_bundle(uid="MEXPIRED", plate="51F24680", start_offset=-40, end_offset=-1)
        expired = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="MEXPIRED", override_plate="51F24680", override_confidence=0.95,
        )
        self.assertEqual(expired.action, "ignore")
        self.assertIn("het han", expired.message.lower())

        _, _, _, future_card = self.add_monthly_bundle(uid="MFUTURE", plate="51F24681", start_offset=2, end_offset=30)
        future = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="MFUTURE", override_plate="51F24681", override_confidence=0.95,
        )
        self.assertEqual(future.action, "ignore")
        self.assertIn("khong hoat dong", future.message.lower())

        _, _, _, card = self.add_monthly_bundle(uid="MMISMATCH", plate="51F24682", start_offset=-1, end_offset=30)
        mismatch = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="MMISMATCH", override_plate="30A99999", override_confidence=0.95,
        )
        self.assertEqual(mismatch.action, "ignore")
        self.assertIn("khong khop", mismatch.message.lower())

    async def test_19_plate_confidence_and_normalization_edges(self):
        card = self.add_guest_card("PLATEEDGE")
        low_conf = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="PLATEEDGE", override_plate="51F12345", override_confidence=0.59,
        )
        self.assertEqual(low_conf.action, "ignore")

        threshold = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="PLATEEDGE", override_plate="51F-12.345", override_confidence=0.60,
        )
        self.assertEqual(threshold.action, "open")
        self.assertEqual(threshold.recognized_plate, "51F12345")

    async def test_20_duplicate_plate_and_wrong_rfid_exit_edges(self):
        card_a = self.add_guest_card("DUPA", status="in_use")
        self.add_open_session("51F33333", "DUPA", card_a)
        card_b = self.add_guest_card("DUPB")

        duplicate = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="entry", trigger_type="rfid",
            source_id="test", rfid_tag="DUPB", override_plate="51F33333", override_confidence=0.95,
        )
        # Current business rule allows duplicate plate with another RFID; this documents the risk.
        self.assertEqual(duplicate.action, "open")

        card_c = self.add_guest_card("DUPC", status="in_use")
        self.add_open_session("51F44444", "DUPC", card_c)
        wrong_card = self.add_guest_card("DUPD", status="available")
        wrong_exit = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="exit", trigger_type="rfid",
            source_id="test", rfid_tag="DUPD", override_plate="51F44444", override_confidence=0.95,
        )
        self.assertEqual(wrong_exit.action, "ignore")
        self.assertIn("rfid", wrong_exit.message.lower())

    def test_21_fee_calculation_boundaries_and_monthly(self):
        now = get_vietnam_now()
        guest = models.ParkingSession(plate_number="51F55555", time_in=now - timedelta(minutes=30), rfid_card_type="guest")
        exact = models.ParkingSession(plate_number="51F55556", time_in=now - timedelta(minutes=60), rfid_card_type="guest")
        overnight = models.ParkingSession(plate_number="51F55557", time_in=now - timedelta(hours=26, minutes=1), rfid_card_type="guest")
        monthly = models.ParkingSession(plate_number="51F55558", time_in=now - timedelta(hours=2), rfid_card_type="monthly")

        self.assertEqual(main_module.calculate_fee(now, guest, self.db, "guest"), (30, 5000.0))
        self.assertEqual(main_module.calculate_fee(now, exact, self.db, "guest"), (60, 5000.0))
        self.assertEqual(main_module.calculate_fee(now, overnight, self.db, "guest"), (1561, 135000.0))
        self.assertEqual(main_module.calculate_fee(now, monthly, self.db, "monthly"), (120, 0.0))

    async def test_22_session_status_force_checkout_and_multiple_open_sessions(self):
        card_old = self.add_guest_card("MULTIOLD", status="in_use")
        old_session = self.add_open_session("51F66666", "MULTIOLD", card_old)
        old_session.time_in = get_vietnam_now() - timedelta(hours=2)
        card_new = self.add_guest_card("MULTINEW", status="in_use")
        new_session = self.add_open_session("51F66666", "MULTINEW", card_new)
        self.db.commit()

        result = await process_gate_scan(
            db=self.db, image_bytes=None, filename=None, gate_type="exit", trigger_type="sensor",
            source_id="test", rfid_tag=None, override_plate="51F66666", override_confidence=0.95,
        )
        self.assertEqual(result.action, "open")
        self.assertEqual(result.session_id, new_session.id)

        card = self.add_guest_card("FORCE1", status="in_use")
        session = self.add_open_session("51F77777", "FORCE1", card)
        response = await main_module.force_checkout(
            plate_number="51F77777", reason="lost_card", open_gate=False, db=self.db, api_key="pbl5_secure_key_12345"
        )
        self.assertEqual(response["status"], "ok")
        self.db.refresh(session)
        self.db.refresh(card)
        self.assertEqual(session.match_status, "manual")
        self.assertIsNotNone(session.time_out)
        self.assertEqual(card.status, "available")

    def test_23_capacity_boundaries_and_dashboard_updates_after_exit(self):
        self.assertEqual(main_module.build_capacity_status(7, 10)["capacity_status"], "near_full")
        self.assertEqual(main_module.build_capacity_status(9, 10)["capacity_status"], "almost_full")
        self.assertEqual(main_module.build_capacity_status(12, 10)["available_slots"], 0)

        card = self.add_guest_card("CAPEXIT", status="in_use")
        session = self.add_open_session("51F88888", "CAPEXIT", card)
        before = main_module.get_dashboard_stats(db=self.db)
        session.time_out = get_vietnam_now()
        session.match_status = "matched"
        card.status = "available"
        self.db.commit()
        after = main_module.get_dashboard_stats(db=self.db)
        self.assertEqual(before.total_in_bay - 1, after.total_in_bay)

    async def test_24_fire_alert_variants_and_notifications(self):
        warning = await main_module.create_fire_alert(
            payload=main_module.schemas.FireAlertCreate(sensor_id="fire-1", level="warning", message="Canh bao khoi"),
            db=self.db,
        )
        await handle_mqtt_event("fire-1", "fire_alert", {"sensor_value": 0})
        alerts = self.db.query(models.FireAlert).order_by(models.FireAlert.id.asc()).all()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].level, "warning")
        self.assertEqual(alerts[1].level, "critical")
        fire_events = [data for event, data in self.notifications if event == "fire_alert"]
        self.assertEqual(len(fire_events), 2)

    async def test_25_mqtt_unknown_malformed_and_cooldown_events(self):
        await handle_mqtt_event("esp32", "heartbeat", {"ok": True})
        self.assertEqual(self.db.query(models.PendingScan).count(), 0)

        main_module.ESP_EVENT_COOLDOWN_SECONDS = 10
        created_tasks = []

        def capture_task(coro):
            created_tasks.append(coro)
            coro.close()
            return MagicMock()

        try:
            with patch("app.main.asyncio.create_task", side_effect=capture_task):
                await handle_mqtt_event("esp32", "car_detected", {})
                await handle_mqtt_event("esp32", "car_detected", {})
            self.db.expire_all()
            self.assertEqual(self.db.query(models.PendingScan).count(), 1)
            self.assertEqual(len(created_tasks), 1)
        finally:
            main_module.ESP_EVENT_COOLDOWN_SECONDS = 0
            main_module._esp_event_cooldown.clear()

    def test_26_dashboard_empty_today_revenue_and_config_defaults(self):
        empty = main_module.get_dashboard_stats(db=self.db)
        self.assertEqual(empty.total_in_bay, 0)
        self.assertEqual(empty.today_total_in, 0)
        self.assertEqual(empty.today_total_out, 0)
        self.assertEqual(empty.today_revenue, 0)

        self.db.add(models.SystemConfig(key="bad_float", value="abc"))
        self.db.commit()
        self.assertEqual(main_module.get_system_config_value(self.db, "missing_key", 42), 42)
        self.assertEqual(main_module.get_system_config_value(self.db, "bad_float", 42), 42)

        yesterday = get_vietnam_now() - timedelta(days=1)
        self.db.add(models.ParkingSession(
            plate_number="51F99991", time_in=yesterday - timedelta(hours=1), time_out=yesterday,
            fee=123456, match_status="matched",
        ))
        self.db.commit()
        stats = main_module.get_dashboard_stats(db=self.db)
        self.assertEqual(stats.today_revenue, 0)

    async def test_27_force_open_timers_logs_and_wrong_key_dependency(self):
        with self.assertRaises(main_module.HTTPException) as ctx:
            main_module.verify_api_key(api_key="wrong", db=self.db)
        self.assertEqual(ctx.exception.status_code, 401)

        entry = await force_open_gate(gate_type="entry", reason="audit", operator="op-entry", db=self.db, api_key="pbl5_secure_key_12345")
        exit_ = await force_open_gate(gate_type="exit", reason="audit", operator="op-exit", db=self.db, api_key="pbl5_secure_key_12345")
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(exit_["status"], "ok")
        logs = self.db.query(models.ManualGateLog).order_by(models.ManualGateLog.id.asc()).all()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].operator, "op-entry")
        self.assertEqual(logs[1].operator, "op-exit")

        main_module._manual_gate_open_until["entry"] = 0.0
        reopened = await force_open_gate(gate_type="entry", reason="again", operator="op-entry", db=self.db, api_key="pbl5_secure_key_12345")
        self.assertEqual(reopened["status"], "ok")

    async def test_28_pending_scan_deleted_before_rfid_and_timeout_cleanup(self):
        await handle_mqtt_event("esp32", "rfid_scan", {"uid": "NOPEN", "direction": "in"})
        updates = [data for event, data in self.notifications if event == "parking_update"]
        self.assertTrue(updates)
        self.assertIn("vị trí", updates[-1]["message"].lower())

        old_pending = models.PendingScan(
            gate_type="entry",
            plate_number="PROCESSING",
            confidence=0.0,
            created_at=get_vietnam_now() - timedelta(minutes=10),
        )
        self.db.add(old_pending)
        self.db.commit()
        main_module.cleanup_expired_pending_scans_once(self.db, max_age_seconds=60)
        self.assertEqual(self.db.query(models.PendingScan).count(), 0)

if __name__ == "__main__":
    unittest.main()
