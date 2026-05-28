import time
import json
import paho.mqtt.client as mqtt

# Cấu hình Broker giống Backend và ESP32
BROKER_HOST = "broker.hivemq.com"
BROKER_PORT = 1883
DEVICE_ID = "esp32-barrier-01"

# Định nghĩa các topic
TOPIC_CAR_DETECTED = f"parking/device/{DEVICE_ID}/event/car_detected"
TOPIC_RFID_SCAN = f"parking/device/{DEVICE_ID}/event/rfid_scan"
TOPIC_FIRE_ALERT = f"parking/device/{DEVICE_ID}/event/fire_alert"

TOPIC_COMMAND_OPEN = f"parking/device/{DEVICE_ID}/command/open_gate"
TOPIC_COMMAND_RESET_FIRE = f"parking/device/{DEVICE_ID}/command/reset_fire"

class MqttHardwareSimulator:
    def __init__(self):
        self.client = mqtt.Client(client_id="esp32-hardware-simulator")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("[SIMULATOR] Kết nối thành công tới MQTT Broker!")
            # Đăng ký nhận lệnh từ Backend
            self.client.subscribe(TOPIC_COMMAND_OPEN)
            self.client.subscribe(TOPIC_COMMAND_RESET_FIRE)
            print(f"[SIMULATOR] Đã đăng ký nhận tin tại topic lệnh của thiết bị.")
        else:
            print(f"[SIMULATOR] Kết nối thất bại với mã lỗi {rc}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        print(f"\n[SIMULATOR RECEIVE] Nhận lệnh từ Backend tại topic [{topic}]:")
        try:
            data = json.loads(payload)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            print(payload)

    def start(self):
        print(f"[SIMULATOR] Đang kết nối tới Broker {BROKER_HOST}:{BROKER_PORT}...")
        self.client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("[SIMULATOR] Đã ngắt kết nối.")

    def trigger_car_detected(self, direction: str):
        payload = {
            "device_id": DEVICE_ID,
            "event_type": "car_detected",
            "direction": direction,
            "gate_id": "gate_in" if direction == "in" else "gate_out"
        }
        print(f"\n[SIMULATOR SEND] Phát hiện xe ở cổng {direction.upper()}...")
        self.client.publish(TOPIC_CAR_DETECTED, json.dumps(payload), qos=1)

    def trigger_rfid_scan(self, uid: str, direction: str):
        payload = {
            "device_id": DEVICE_ID,
            "uid": uid,
            "direction": direction,
            "gate_id": "gate_in" if direction == "in" else "gate_out"
        }
        print(f"\n[SIMULATOR SEND] Quẹt thẻ RFID (UID: {uid}) tại cổng {direction.upper()}...")
        self.client.publish(TOPIC_RFID_SCAN, json.dumps(payload), qos=1)

    def trigger_fire_alert(self):
        payload = {
            "device_id": DEVICE_ID,
            "sensor_value": 0,
            "message": "Fire sensor triggered in simulator!"
        }
        print(f"\n[SIMULATOR SEND] PHÁT HIỆN HỎA HOẠN!")
        self.client.publish(TOPIC_FIRE_ALERT, json.dumps(payload), qos=1)

if __name__ == "__main__":
    sim = MqttHardwareSimulator()
    sim.start()
    
    time.sleep(2)  # Đợi kết nối ổn định
    
    print("\n=======================================================")
    print("  TRÌNH GIẢ LẬP PHẦN CỨNG BẰNG MQTT")
    print("=======================================================")
    print("Nhập số tương ứng với hành động bạn muốn giả lập:")
    print("1. Xe đè cảm biến cổng VÀO (IR IN)")
    print("2. Quẹt thẻ cổng VÀO (RFID IN) - UID: E9B8A7C6 (Thẻ khách/thẻ mẫu)")
    print("3. Xe đè cảm biến cổng RA (IR OUT)")
    print("4. Quẹt thẻ cổng RA (RFID OUT) - UID: E9B8A7C6")
    print("5. Giả lập báo động cháy (FIRE ALERT)")
    print("0. Thoát trình giả lập")
    print("=======================================================")
    
    try:
        while True:
            choice = input("\nHành động: ").strip()
            if choice == "1":
                sim.trigger_car_detected("in")
            elif choice == "2":
                sim.trigger_rfid_scan("E9B8A7C6", "in")
            elif choice == "3":
                sim.trigger_car_detected("out")
            elif choice == "4":
                sim.trigger_rfid_scan("E9B8A7C6", "out")
            elif choice == "5":
                sim.trigger_fire_alert()
            elif choice == "0":
                break
            else:
                print("Lựa chọn không hợp lệ, hãy nhập từ 0 đến 5.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
