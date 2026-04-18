#ifndef API_CLIENT_H
#define API_CLIENT_H

#include <Arduino.h>

String postJson(const char *url, const String &json, int &statusCode);
void sendCarDetected(const String &direction, const String &gateId);
void sendRfidScan(const String &uid, const String &directionHint);
void sendFireAlert(const String &deviceId, int sensorValue);

#endif

