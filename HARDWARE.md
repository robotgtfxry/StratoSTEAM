# Hardware — mapa czujników

> **Architektura systemu:**
> - **ESP32-S3 (balon)** — węzeł radiowy: GPS (NEO-M8N) + LoRa (SX1278), retransmisja danych z RPi5
> - **Raspberry Pi 5 (balon)** — węzeł pomiarowy: czujniki atmosferyczne, IMU, kamera, RTL-SDR (odbiór sygnału HF z ziemi)
> - **Raspberry Pi 5 (ziemia)** — stacja naziemna: LoRa RX/TX, nadajnik HF (AD9833 + RD06HHF1)
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

## Kamera — RPi Camera Module (CSI cam0, RPi5 balon)

| Złącze | RPi5               |
|--------|--------------------|
| CSI    | CAM0 (15-pin, pin 1)|

> RPi5 (balon). Ciągłe nagrywanie H.264 na dysk (`/home/pi/cam/`).  
> Na żądanie z Flutter: zdjęcie 160×120 JPEG, chunki po 140 bajtów (base64), przesyłane przez UART → LoRa → backend.  
> Dysk monitorowany: `shutil.disk_usage()`, dane `dsku`/`dskf` w beaconie ESP32.

---

## RTL-SDR — odbiornik HF jonosferyczny (USB, RPi5 balon)

| Złącze    | RPi5               |
|-----------|--------------------|
| USB       | dowolny port USB   |
| Antena    | wejście SMA dongle |

> RPi5 (balon). Odbiera sygnał HF z nadajnika naziemnego (AD9833 + RD06HHF1).  
> Biblioteka: `pyrtlsdr`. Tune offset: −100 kHz poniżej docelowej częstotliwości (unikanie DC spike).  
> FFT z oknem Blackmana → power w ±15 binach wokół nośnej → wynik w dBFS.  
> Pomiar co 10 s, wysyłany do ESP32 jako pole `hfdb` w JSON przez UART → LoRa → backend → Flutter (wykres dBFS vs wysokość).

---

## AD9833 + RD06HHF1 — nadajnik HF jonosferyczny (SPI1, RPi5 ziemia)

| Pin AD9833 | RPi5 BCM              |
|------------|-----------------------|
| SCLK       | SPI1 CLK              |
| MOSI       | SPI1 MOSI             |
| FSYNC/CS   | SPI1 CS1              |
| PTT        | GPIO24 (pin 18)       |
| VCC        | 3.3V                  |
| GND        | GND                   |

> RPi5 (ziemia). Generuje sygnał HF (domyślnie 7.1 MHz / pasmo 40m), wzmacniany przez RD06HHF1.  
> Komenda start/stop/set_freq pochodzi z backendu (Flutter → backend → rpi-ground).  
> RTL-SDR na balonie mierzy siłę tego sygnału (dBFS) i odsyła przez LoRa — eksperyment jonosferyczny.

---

## UART RPi5 ↔ ESP32 (dwukierunkowy)

| Sygnał           | RPi5 BCM            | ESP32 GPIO | Kierunek       | Port RPi5      |
|------------------|---------------------|------------|----------------|----------------|
| TX czujników     | GPIO14 (TXD, pin 8) | GPIO3 (RX) | RPi5 → ESP32   | /dev/ttyAMA0   |
| RX komend        | GPIO15 (RXD, pin 10)| GPIO14 (TX)| ESP32 → RPi5   | /dev/ttyAMA0   |

> Prędkość: 115200 baud, 8N1. RPi5 wysyła line-delimited JSON co 5 s.  
> Dane TX: temp, hum, pres (BME280), p2, alt2 (MS5611), roll, pit, yaw, ax, ay, az (BNO085), vbat, imA (INA219), dsku, dskf (dysk), hfdb (SDR dBFS, opcjonalne).  
> Dane RX: komendy JSON od ESP32 — `{"cmd":"photo"}`, `{"cmd":"cam_rec","on":true/false}`, shutdown request.

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
