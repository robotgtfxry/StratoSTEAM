# Hardware — mapa czujników

> **Architektura systemu:**
> - **ESP32-S3** — węzeł radiowy: wyłącznie GPS (NEO-M8N) i LoRa (SX1278)
> - **Raspberry Pi 5** — węzeł pomiarowy: wszystkie czujniki atmosferyczne, IMU, kamera, APRS
> - Limit wagowy ładunku: **1 kg** (większa pojemność baterii)

---

## BME280 — temperatura, ciśnienie, wilgotność (I2C 0x76)

| Pin modułu | RPi5 BCM        |
|------------|-----------------|
| SDA        | GPIO2 (pin 3)   |
| SCL        | GPIO3 (pin 5)   |
| VCC        | 3.3V (pin 1)    |
| GND        | GND (pin 6)     |

> Tylko RPi5.

---

## INA219 — napięcie i prąd baterii (I2C 0x40, bocznik 0.1 Ω)

| Pin modułu | RPi5 BCM        |
|------------|-----------------|
| SDA        | GPIO2 (pin 3)   |
| SCL        | GPIO3 (pin 5)   |
| VCC        | 3.3V (pin 1)    |
| GND        | GND (pin 6)     |

> Tylko RPi5.

---

## MS5611 — precyzyjne ciśnienie / wysokość (I2C 0x77)

| Pin modułu | RPi5 BCM        |
|------------|-----------------|
| SDA        | GPIO2 (pin 3)   |
| SCL        | GPIO3 (pin 5)   |
| VCC        | 3.3V (pin 1)    |
| GND        | GND (pin 6)     |

> Tylko RPi5.

---

## BNO085 — IMU 9-DOF (I2C 0x4A)

| Pin modułu | RPi5 BCM        |
|------------|-----------------|
| SDA        | GPIO2 (pin 3)   |
| SCL        | GPIO3 (pin 5)   |
| VCC        | 3.3V (pin 1)    |
| GND        | GND (pin 6)     |

> Tylko RPi5. Dane: roll, pitch, yaw, akcelerometr (x/y/z).

---

## GPS NEO-M8N — pozycja, wysokość, prędkość (UART)

| Pin GPS | ESP32 GPIO  | Opis            |
|---------|-------------|-----------------|
| TX      | GPIO4 (RX)  | odczyt NMEA     |
| VCC     | 3.3V        |                 |
| GND     | GND         |                 |

> Tylko ESP32 (odczyt jednokierunkowy — RX GPS niepodpięty). Dane GPS dołączane do każdego pakietu LoRa.

---

## LoRa SX1278 — telemetria 433 MHz (SPI)

| Pin LoRa | ESP32 GPIO |
|----------|------------|
| SCK      | GPIO12     |
| MOSI     | GPIO11     |
| MISO     | GPIO13     |
| NSS/CS   | GPIO10     |
| DIO0     | GPIO9      |
| RST      | GPIO8      |
| VCC      | 3.3V       |
| GND      | GND        |

> Tylko ESP32. DIO0 i RST w pełni używane przez bibliotekę Arduino-LoRa.

---

## AD9833 — beacon APRS 144.800 MHz (SPI1)

| Pin AD9833 | RPi5 BCM              |
|------------|-----------------------|
| SCLK       | GPIO21 (pin 40)       |
| MOSI       | GPIO20 (pin 38)       |
| FSYNC/CS   | GPIO16 (CE2, pin 36)  |
| PTT        | GPIO24 (pin 18)       |
| VCC        | 3.3V (pin 1)          |
| GND        | GND (pin 6)           |

> Tylko RPi5. PTT steruje wyjściem RF — HIGH = nadawanie.

---

## UART RPi5 → ESP32 (dane czujników)

| Sygnał       | RPi5 BCM           | ESP32 GPIO | Kierunek       | Port RPi5      |
|--------------|--------------------|------------|----------------|----------------|
| TX czujników | GPIO14 (TXD, pin 8)| GPIO3 (RX) | RPi5 → ESP32   | /dev/ttyAMA0   |

> Prędkość: 115200 baud, 8N1. RPi5 wysyła line-delimited JSON co 5 s.  
> Dane: temp, hum, pres (BME280), p2, alt2 (MS5611), roll, pit, yaw, ax, ay, az (BNO085), vbat, imA (INA219).

---

## Sygnały ESP32 ↔ RPi5 (GPIO)

| Sygnał         | RPi5 BCM          | ESP32 GPIO | Kierunek               |
|----------------|-------------------|------------|------------------------|
| RPI_ALIVE      | GPIO26 (pin 37)   | GPIO6      | RPi5 → ESP32           |
| ESP32_SHTDN    | GPIO6 (pin 31)    | GPIO7      | ESP32 → RPi5           |
| RPI_PWR        | —                 | GPIO5      | ESP32 → zasilanie RPi5 |

---

## Tylko ESP32 (GPIO)

| Element     | ESP32 GPIO | Opis                                               |
|-------------|------------|----------------------------------------------------|
| Buzzer      | GPIO2      | alert audio (PWM 2800 Hz)                          |
| LED R       | GPIO17     | status (PWM)                                       |
| LED G       | GPIO18     | status (PWM)                                       |
| LED B       | GPIO20     | status (PWM)                                       |
| ADC baterii | GPIO1      | napięcie baterii (backup gdy RPi5 wyłączona)       |
