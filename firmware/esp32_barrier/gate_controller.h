#ifndef GATE_CONTROLLER_H
#define GATE_CONTROLLER_H

void initGateHardware();

void openGateIn();
void closeGateIn();
void openGateOut();
void closeGateOut();

void setAlertRelays(bool on);
void handleAutoClose(bool fireAlertActive);

#endif

