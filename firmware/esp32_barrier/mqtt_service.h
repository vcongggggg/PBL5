#ifndef MQTT_SERVICE_H
#define MQTT_SERVICE_H

#include <Arduino.h>

void setupMqtt();
void loopMqtt();
void publishCarDetected(const String &direction);
void publishRfidScan(const String &uid, const String &directionHint);
void publishFireAlert(int sensorValue);

#endif
