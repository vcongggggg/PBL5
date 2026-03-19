## ESP32 Component Test Guide

Bo sketch test rieng cho tung phan:

- `test_ir_sensor/test_ir_sensor.ino`
- `test_button_manual/test_button_manual.ino`
- `test_lcd_i2c/test_lcd_i2c.ino`
- `test_servo/test_servo.ino`

## Thu tu test khuyen nghi

1. Test IR sensor
2. Test button
3. Test LCD I2C
4. Test servo (sau cung)

## 1) IR sensor

- Noi: IR OUT -> GPIO27, VCC -> 3V3/5V, GND -> GND.
- Nap `test_ir_sensor.ino`.
- Mo Serial Monitor (115200), che/mo tay truoc cam bien.
- Ket qua: in `IR state: HIGH/LOW`.

Neu logic nguoc voi mong muon, ghi chu lai de sua trong sketch chinh.

## 2) Button manual

- Noi: 1 chan nut -> GPIO26, chan con lai -> GND.
- Nap `test_button_manual.ino`.
- Mo Serial Monitor (115200).
- Nhan nut: `PRESSED`, tha nut: `RELEASED`.

## 3) LCD I2C

- Noi: SDA -> GPIO21, SCL -> GPIO22, VCC -> 5V (hoac 3V3), GND -> GND.
- Nap `test_lcd_i2c.ino`.
- LCD hien 4 dong test.

Neu LCD khong hien, sua dia chi trong sketch:
- Tu `0x27` sang `0x3F`.

## 4) Servo

- Noi: signal -> GPIO14.
- Nguon servo 5V rieng khuyen nghi, va noi chung GND voi ESP32.
- Nap `test_servo.ino`.
- Servo quay qua lai goc 0 <-> 80.

## Sau khi test xong

Neu tat ca deu OK, nap lai sketch tong:
- `esp32_barrier.ino`

