import asyncio

gate_locks = {
    "entry": asyncio.Lock(),
    "exit": asyncio.Lock()
}

esp32_ip = None

_esp_event_cooldown = {}
ESP_EVENT_COOLDOWN_SECONDS = 3.0

_manual_gate_open_until = {}
