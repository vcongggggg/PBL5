#include <HTTPClient.h>

#include "api_client.h"
#include "config.h"
#include "gate_controller.h"
#include "network_service.h"

String postJson(const char *url, const String &json, int &statusCode) {
  statusCode = -1;
  if (!isWifiConnected()) {
    return "";
  }

  HTTPClient http;
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", API_KEY);
  statusCode = http.POST(json);
  String resp = http.getString();
  http.end();
  return resp;
}

void sendCarDetected(const String &direction, const String &gateId) {
  int code;
  String body = "{";
  body += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  body += "\"event_type\":\"car_detected\",";
  body += "\"direction\":\"" + direction + "\",";
  body += "\"gate_id\":\"" + gateId + "\"";
  body += "}";

  String url = "http://" + String(backend_ip) + ":8000/api/esp/events";
  String resp = postJson(url.c_str(), body, code);
  Serial.printf("EVENT %s -> %d\n", direction.c_str(), code);
  Serial.println(resp);

  if (code == 200 && resp.indexOf("\"action\":\"open\"") != -1) {
    if (direction == "in") {
      openGateIn();
    } else {
      openGateOut();
    }
  }
}

bool sendRfidScan(const String &uid, const String &directionHint) {
  int code;
  String gateId = (directionHint == "in") ? "gate_in" : "gate_out";
  String body = "{";
  body += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  body += "\"uid\":\"" + uid + "\",";
  body += "\"direction\":\"" + directionHint + "\",";
  body += "\"gate_id\":\"" + gateId + "\"";
  body += "}";

  String url = "http://" + String(backend_ip) + ":8000/api/esp/rfid";
  String resp = postJson(url.c_str(), body, code);
  Serial.printf("RFID UID=%s -> %d\n", uid.c_str(), code);
  Serial.println(resp);

  bool accepted = (code == 200 && resp.indexOf("\"action\":\"open\"") != -1);
  if (accepted) {
    if (directionHint == "in") {
      openGateIn();
    } else {
      openGateOut();
    }
  }
  return accepted;
}

void sendFireAlert(const String &deviceId, int sensorValue) {
  int code;
  String body = "{";
  body += "\"device_id\":\"" + deviceId + "\",";
  body += "\"sensor_value\":" + String(sensorValue) + ",";
  body += "\"message\":\"Fire sensor triggered\"";
  body += "}";

  String url = "http://" + String(backend_ip) + ":8000/api/esp/fire-alert";
  String resp = postJson(url.c_str(), body, code);
  Serial.printf("FIRE ALERT -> %d\n", code);
  Serial.println(resp);
}
