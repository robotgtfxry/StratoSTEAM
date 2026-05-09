# Hardware — mapa czujników

---

## BME280 — temperatura, ciśnienie, wilgotność (I2C 0x76)

| Pin modułu | RPi5 BCM | RPi5 pin fiz. | ESP32 GPIO |
|------------|----------|---------------|------------|
| SDA        | GPIO2    | pin 3         | GPIO15     |
| SCL        | GPIO3    | pin 5         | GPIO16     |
| VCC        | 3.3V     | pin 1         | 3.3V       |
| GND        | GND      | pin 6         | GND        |

> Jeden fizyczny chip podpięty do obu płytek na wspólnej szynie I2C. Tylko jeden master aktywny na raz (przełączanie przez RPI_ALIVE).

---

## INA219 — napięcie i prąd baterii (I2C 0x40, bocznik 0.1 Ω)

| Pin modułu | RPi5 BCM | RPi5 pin fiz. | ESP32 GPIO |
|------------|----------|---------------|------------|
| SDA        | GPIO2    | pin 3         | GPIO15     |
| SCL        | GPIO3    | pin 5         | GPIO16     |
| VCC        | 3.3V     | pin 1         | 3.3V       |
| GND        | GND      | pin 6         | GND        |

> Tak samo jak BME280 — jeden chip, wspólna szyna I2C.

---

## MS5611 — precyzyjne ciśnienie / wysokość (I2C 0x77)

| Pin modułu | RPi5 BCM | RPi5 pin fiz. |
|------------|----------|---------------|
| SDA        | GPIO2    | pin 3         |
| SCL        | GPIO3    | pin 5         |
| VCC        | 3.3V     | pin 1         |
| GND        | GND      | pin 6         |

> Tylko RPi5. ESP32 nie ma dostępu do MS5611.

---

## BNO085 — IMU 9-DOF (I2C 0x4A)

| Pin modułu | RPi5 BCM | RPi5 pin fiz. |
|------------|----------|---------------|
| SDA        | GPIO2    | pin 3         |
| SCL        | GPIO3    | pin 5         |
| VCC        | 3.3V     | pin 1         |
| GND        | GND      | pin 6         |

> Tylko RPi5. Dane: roll, pitch, yaw, akcelerometr (x/y/z).

---

## GPS NEO-M8N — pozycja, wysokość, prędkość (UART)

### RPi5

| Pin GPS | RPi5 BCM | RPi5 pin fiz. | Port         |
|---------|----------|---------------|--------------|
| TX      | GPIO15 (RXD) | pin 10   | /dev/ttyAMA0 |
| RX      | GPIO14 (TXD) | pin 8    | /dev/ttyAMA0 |
| VCC     | 3.3V     | pin 1         |              |
| GND     | GND      | pin 6         |              |

### ESP32 (backup — działa gdy RPi5 wyłączone)

| Pin GPS | ESP32 GPIO |
|---------|------------|
| TX      | GPIO4 (RX) |
| VCC     | 3.3V       |
| GND     | GND        |

> ESP32 podłączone tylko do TX GPS (odczyt jednokierunkowy). RX GPS niepodpięty do ESP32.

---

## LoRa SX1278 — telemetria 433 MHz (SPI)

| Pin LoRa | RPi5 BCM    | RPi5 pin fiz. | ESP32 GPIO |
|----------|-------------|---------------|------------|
| SCK      | GPIO11      | pin 23        | GPIO12     |
| MOSI     | GPIO10      | pin 19        | GPIO11     |
| MISO     | GPIO9       | pin 21        | GPIO13     |
| NSS/CS   | GPIO8 (CE0) | pin 24        | GPIO10     |
| DIO0     | GPIO25      | pin 22        | GPIO9      |
| RST      | —           | niepodpięty   | GPIO8      |
| VCC      | 3.3V        | pin 1         | 3.3V       |
| GND      | GND         | pin 6         | GND        |

> RPi5: soft reset przez SPI, DIO0 zdefiniowany w config ale kod używa pollingu.  
> ESP32: DIO0 i RST w pełni używane przez bibliotekę Arduino-LoRa.

---

## AD9833 — beacon APRS 144.800 MHz (SPI1)

| Pin AD9833 | RPi5 BCM    | RPi5 pin fiz. |
|------------|-------------|---------------|
| SCLK       | GPIO21      | pin 40        |
| MOSI       | GPIO20      | pin 38        |
| FSYNC/CS   | GPIO16 (CE2)| pin 36        |
| PTT        | GPIO24      | pin 18        |
| VCC        | 3.3V        | pin 1         |
| GND        | GND         | pin 6         |

> PTT steruje wyjściem RF — HIGH = nadawanie. Pin GPIO24 nie ma wpisu w config.py (używana wartość domyślna z kodu).

---

## Sygnały ESP32 ↔ RPi5 (GPIO)

| Sygnał         | RPi5 BCM | RPi5 pin fiz. | ESP32 GPIO | Kierunek         |
|----------------|----------|---------------|------------|------------------|
| RPI_ALIVE      | GPIO26   | pin 37        | GPIO6      | RPi5 → ESP32     |
| ESP32_SHTDN    | GPIO6    | pin 31        | GPIO7      | ESP32 → RPi5     |
| RPI_PWR        | —        | —             | GPIO5      | ESP32 → zasilanie RPi5 |

---

## Tylko ESP32 (GPIO)

| Element     | ESP32 GPIO | Opis                  |
|-------------|------------|-----------------------|
| Buzzer      | GPIO2      | alert audio (PWM 2800 Hz) |
| LED R       | GPIO17     | status (PWM)          |
| LED G       | GPIO18     | status (PWM)          |
| LED B       | GPIO20     | status (PWM)          |
| ADC baterii | GPIO1      | napięcie baterii      |
