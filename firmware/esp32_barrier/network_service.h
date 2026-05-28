#ifndef NETWORK_SERVICE_H
#define NETWORK_SERVICE_H

extern char backend_ip[40];
extern char mqtt_broker[40];
extern int mqtt_port;

void connectWifi();
bool isWifiConnected();
void checkWifiReconnect();
void updateBackendIp(String new_ip);
void updateMqttBroker(String new_broker, int new_port);

#endif

