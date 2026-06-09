#ifndef MQTT_SERVICE_H
#define MQTT_SERVICE_H

#include <Arduino.h>

void setupMqtt();
void loopMqtt();
void publishCarDetected(const String &direction);
bool publishRfidScan(const String &uid, const String &directionHint);
void publishFireAlert(int sensorValue);
void publishFireTelemetry(int digitalValue, int analogValue, bool fireDetected, bool fireAlertActive);

#endif
