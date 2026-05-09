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

## SPI — LoRa SX1278

| Pin LoRa | RPi5 BCM | RPi5 pin fizyczny | ESP32 GPIO |
|----------|----------|-------------------|------------|
| SCK      | GPIO11   | pin 23            | GPIO12     |
| MOSI     | GPIO10   | pin 19            | GPIO11     |
| MISO     | GPIO9    | pin 21            | GPIO13     |
| NSS/CS   | GPIO8 (CE0) | pin 24         | GPIO10     |
| DIO0     | GPIO25   | pin 22            | GPIO9      |
| RST      | —        | niepodpięty       | GPIO8      |

> RPi5 nie używa RST — soft reset przez SPI. DIO0 zdefiniowany w config, ale kod używa pollingu (pin fizycznie nieużywany).

## SPI — pozostałe

| Moduł  | Podłączony do | Opis |
|--------|---------------|------|
| AD9833 | RPi5 SPI Bus 1, CE2 (GPIO16, pin 36) | beacon APRS 144.800 MHz |
