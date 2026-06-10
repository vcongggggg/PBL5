# Cau truc thu muc workspace

```text
PBL5/
|-- backend/
|   |-- app/
|   |   |-- core/
|   |   |   |-- __init__.py
|   |   |   |-- schema_sync.py
|   |   |   |-- security.py
|   |   |   |-- string_utils.py
|   |   |   `-- time_utils.py
|   |   |-- integrations/
|   |   |   |-- __init__.py
|   |   |   `-- mqtt_manager.py
|   |   |-- routers/
|   |   |-- services/
|   |   |-- database.py
|   |   |-- main.py
|   |   |-- models.py
|   |   |-- schemas.py
|   |   `-- state.py
|   |-- models/
|   |   `-- paddleocr_vn_plate_rec/
|   |       |-- inference.json
|   |       |-- inference.pdiparams
|   |       |-- inference.yml
|   |       `-- vn_plate_dict.txt
|   |-- uploads/
|   |-- .env.example
|   |-- .gitignore
|   |-- pbl5.db
|   |-- requirements.txt
|-- firmware/
|   `-- esp32_barrier/
|       |-- buzzer_service.cpp
|       |-- buzzer_service.h
|       |-- config.h
|       |-- esp32_barrier.ino
|       |-- gate_controller.cpp
|       |-- gate_controller.h
|       |-- mqtt_service.cpp
|       |-- mqtt_service.h
|       |-- network_service.cpp
|       |-- network_service.h
|       |-- README.md
|       |-- rfid_service.cpp
|       |-- rfid_service.h
|       `-- TEST_GUIDE.md
|-- frontend/
|   |-- app.js
|   |-- index.html
|   `-- style.css
|-- test/
|-- TrainPaddle/
|-- .gitignore
|-- .gitmodules
|-- best.pt
|-- README.md
```

## Tom tat nhanh

- `backend/`: API Python/FastAPI, database, routers, services, model OCR bien so va anh upload.
- `frontend/`: giao dien web tinh gom HTML, CSS, JavaScript.
- `firmware/`: ma ESP32 dieu khien barrier, RFID, MQTT, network va buzzer.
- `test/`: cac sketch/test phan cung, simulator MQTT va cau hinh Wokwi.
- `TrainPaddle/`: dataset, PaddleOCR source, pretrained model va workspace huan luyen OCR.
- `docs/` va cac file Markdown goc: tai lieu kien truc, README va huong dan deploy.
