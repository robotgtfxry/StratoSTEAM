# Hardware — mapa czujników

## Wspólna szyna I2C (ESP32 GPIO15/16 ↔ RPi5 SDA/SCL)

| Czujnik | Adres | Dane |
|---------|-------|------|
| BME280  | 0x76  | temperatura, ciśnienie, wilgotność |
| INA219  | 0x40  | napięcie i prąd baterii (bocznik 0.1 Ω) |

## Tylko RPi5 (I2C Bus 1)

| Czujnik | Adres | Dane |
|---------|-------|------|
| MS5611  | 0x77  | precyzyjne ciśnienie / wysokość |
| BNO085  | 0x4A  | IMU 9-DOF (akcelerometr, żyroskop, magnetometr) |

## Tylko RPi5 (UART)

| Moduł     | Port            | Dane |
|-----------|-----------------|------|
| GPS NEO-M8N | /dev/ttyAMA0 9600 | pozycja, wysokość, prędkość, kurs |

## Tylko ESP32 (GPIO)

| Element  | Pin    | Opis |
|----------|--------|------|
| GPS NEO-M8N | GPIO4 RX | pozycja (backup gdy RPi off) |
| Buzzer   | GPIO2  | alert audio (PWM) |
| LED R    | GPIO17 | status (PWM) |
| LED G    | GPIO18 | status (PWM) |
| LED B    | GPIO20 | status (PWM) |
| ADC baterii | GPIO1 | napięcie baterii |

## SPI

| Moduł       | Podłączony do | Opis |
|-------------|---------------|------|
| LoRa SX1278 | ESP32 GPIO8–13 | telemetria 433 MHz (backup) |
| LoRa SX1278 | RPi5 SPI Bus 0 | telemetria 433 MHz (główny) |
| AD9833      | RPi5 SPI Bus 1 | beacon APRS 144.800 MHz |
