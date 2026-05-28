#ifndef NETWORK_SERVICE_H
#define NETWORK_SERVICE_H

extern char backend_ip[40];

void connectWifi();
bool isWifiConnected();
void checkWifiReconnect();

#endif

