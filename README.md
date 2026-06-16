# Smart Parking System with License Plate Recognition

Academic PBL5 project: a smart parking prototype that combines an ESP32 barrier controller, RFID verification, a FastAPI backend, a web dashboard, and AI license plate recognition.

## Highlights

- ESP32-based barrier control with IR vehicle detection, RFID workflow, servo gate control, and manual open support.
- FastAPI backend for parking sessions, gate triggers, vehicle check-in/check-out, RFID events, fire alerts, and dashboard data.
- License plate recognition pipeline using YOLO for plate detection, PaddleOCR for OCR, and OpenCV preprocessing.
- Web dashboard for monitoring parking activity, gate operations, camera/OCR results, and alerts.
- Database-backed business logic with SQLAlchemy and SQLite for development, with MySQL-ready configuration.

## My Contribution

- Built the ESP32/RFID integration flow and barrier-control firmware workflow.
- Implemented backend and database logic for RFID events, parking sessions, gate triggers, and fire alerts.
- Built dashboard flows for monitoring vehicles, RFID status, gate actions, and recognition results.
- Integrated OCR results into the parking-session workflow and validation logic.

## System Overview

```text
ESP32 + RFID + IR Sensor
        |
        | HTTP events
        v
FastAPI Backend ---- SQLAlchemy ---- SQLite / MySQL-ready database
        |
        | REST / WebSocket-style updates
        v
Web Dashboard
        ^
        |
Camera image -> YOLO plate detection -> PaddleOCR recognition -> backend validation
```

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy, Uvicorn
- Database: SQLite for development, MySQL-ready configuration
- Frontend: HTML, CSS, JavaScript
- AI / Computer Vision: OpenCV, YOLO, PaddleOCR
- IoT / Embedded: ESP32, Arduino C++, RFID RC522, IR sensor, servo barrier

## Repository Structure

```text
backend/
  app/
    ai_service.py      # Plate detection/OCR service
    database.py        # Database configuration
    main.py            # FastAPI application and routes
    models.py          # SQLAlchemy models
    schemas.py         # Request/response schemas
  requirements.txt

firmware/
  esp32_barrier/
    esp32_barrier.ino  # ESP32 barrier firmware
    README.md          # Wiring and firmware guide
    TEST_GUIDE.md

frontend/
  index.html           # Dashboard UI
```

## Main Features

### Parking Workflow

- Detect vehicle arrival through IR sensor events.
- Read RFID card data and send events to the backend.
- Capture/process plate recognition results.
- Create or close parking sessions based on RFID, vehicle status, and plate validation.
- Control barrier opening through backend-approved events.

### Dashboard

- View current parking activity and system state.
- Monitor vehicle sessions and gate actions.
- Trigger or inspect recognition workflows.
- Track alerts such as fire warning events.

### AI Recognition

- Detect license plate region with YOLO.
- Crop and preprocess the plate image with OpenCV.
- Recognize text using PaddleOCR.
- Normalize and validate OCR output before applying parking logic.

### ESP32 Firmware

- Connects to Wi-Fi and sends hardware events to FastAPI.
- Reads IR sensor and RFID-related events.
- Controls servo barrier actions.
- Supports manual open workflow.

## Run Backend Locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload
```

Open:

- API docs: http://127.0.0.1:8000/docs
- Backend root: http://127.0.0.1:8000

## Run Frontend

Open `frontend/index.html` in a browser, or serve it with a simple static server if browser security settings block local requests.

## Firmware Setup

See [firmware/esp32_barrier/README.md](firmware/esp32_barrier/README.md) for wiring, ESP32 pinout, Arduino library requirements, and firmware configuration.

Important values to configure in `esp32_barrier.ino`:

- Wi-Fi SSID/password
- Backend event URL
- Backend manual-open URL
- Device ID

## Notes

- Local database files, Python bytecode, generated artifacts, and large local model files are ignored by `.gitignore`.
- `backend/yolov8n.pt` is kept as a small demo model weight; custom model weights should stay outside Git or use a documented download step.
- Configure a different database through `DATABASE_URL`; SQLite is the default for local development.
- The current project is an academic prototype, not a production parking system.
