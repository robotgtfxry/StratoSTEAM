# Hardware — mapa czujników

> **Architektura systemu:**
> - **ESP32-S3 (balon)** — węzeł radiowy: GPS (NEO-M8N) + LoRa (SX1278), retransmisja danych z RPi5
> - **Raspberry Pi 5 (balon)** — węzeł pomiarowy: czujniki atmosferyczne, IMU, kamera CSI, 1× ESP32-CAM (zasilanie 5V + status UART3), RTL-SDR (odbiór sygnału HF z ziemi), 2× przekaźnik HJR1-2C L-3VDC (system zwalniania linek)
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

> RPi5 (balon). Ciągłe nagrywanie H.264 4K (3840×2160, 15 Mbps) na dysk — katalog z `CAM_RECORD_DIR` (domyślnie `/home/pi/stratosteam-video`).  
> Na żądanie z Flutter: zdjęcie 160×120 JPEG, chunki po 140 bajtów (base64), przesyłane przez UART → LoRa → backend.  
> Dysk monitorowany: `shutil.disk_usage()`, dane `dsku`/`dskf` w beaconie ESP32 (pole `d`).  
> 15 Mbps przy 4K to ~54 GB na 8 h lotu — potrzebna karta 64 GB lub większa.

---

## ESP32-CAM — podłączenie bezpośrednie do RPi5 (balon)

Na balonie leci **jedna** kamera ESP32-CAM (AI-Thinker, czujnik **OV3660**). Zasilana **bezpośrednio** z szyny 5 V RPi — działa zawsze, gdy RPi ma prąd. Status idzie przez **sprzętowy UART3** RPi 5.

| Sygnał       | RPi5                    | ESP32-CAM       | Uwagi                                  |
|--------------|-------------------------|-----------------|----------------------------------------|
| Zasilanie    | 5V (pin 2 lub 4)        | 5V              | szczyty ~300 mA, krótki gruby przewód  |
| Masa         | GND (pin 6, 9 lub 14)   | GND             | masa wspólna                           |
| Status (RX)  | GPIO9 (pin 21) = UART3 RX | U0T (GPIO1, TX) | 115200 baud, 3.3V ↔ 3.3V, bez level-shiftera |

```
 RPi5 pin 2  (5V)   ──────────────── 5V    ESP32-CAM
 RPi5 pin 6  (GND)  ──────────────── GND
 RPi5 pin 21 (GPIO9)◄──────────────── U0T (GPIO1)
```

Wymagane w `/boot/firmware/config.txt` (sekcja `[all]`):
```
dtoverlay=uart3-pi5
```
→ port `/dev/ttyAMA3`. W `rpi-air/config.py`: `ESPCAM_UART_PORT = "/dev/ttyAMA3"`, `ESPCAM_PWR_PIN = None`.

> Nie podłączaj U0R (GPIO3) ani GPIO0 — tylko do programowania. GPIO8 (pin 24) = UART3 TX — zarezerwowany przez overlay, nic do niego nie podłączaj.
> Komenda LoRa `espcam_pwr` jest przy tym podłączeniu ignorowana (tylko log). Żeby wrócić do przełączania MOSFET-em: ustaw `ESPCAM_PWR_PIN` na numer GPIO (np. 17) i użyj tranzystora logic-level ≥1 A (AO3400 / IRLZ44N — nie BSS138, za słaby).

### Oprogramowanie ESP32-CAM (`espcam/src/main.cpp`)

- Ciągle nagrywa MJPEG AVI (VGA 640×480, ~9.5 fps, `JPEG_QUALITY 10`) na kartę SD
- Dzieli plik co `FILE_SPLIT_S` (5 min) — przy utracie zasilania tracisz maksymalnie jeden segment
- Przy każdym starcie tworzy nowy katalog sesji: `/CAM/S000`, `/CAM/S001`, …
- Bez karty SD kamera działa dalej i co 30 s sprawdza, czy karta się pojawiła — wtedy sama zaczyna nagrywać
- Karta: **FAT32, ≤ 32 GB** (SDHC)
- **Bez WiFi** — tylko zapis na SD
- LED statusu: mała czerwona dioda **GPIO33** (z tyłu płytki), co 2 s: 1× = OK, 2× = brak SD, 3× = błąd kamery. Lampa błyskowa GPIO4 jest zawsze zgaszona.

**Wgrywanie:** `cd espcam && pio run -t upload` (przez nakładkę ESP32-CAM-MB / USB)

**Status przez UART** — co 5 s linia z prefiksem `$S`:
```
$S{"ok":1,"rec":1,"sd":1,"n":1234,"mb":7800,"fps":9.5}
```
`ok` = kamera działa, `rec` = trwa zapis, `sd` = karta zamontowana, `n` = klatki, `mb` = wolne MB, `fps` = klatki/s.
Linie bez `$S` (boot, debug) są ignorowane. `EspCamMonitor` (pyserial, `/dev/ttyAMA3`) dokłada `"ec": [ok, rec, klatki, wolne_MB]` do pakietu UART → ESP32-S3 → LoRa (pole `c`) → backend → Flutter. Gdy kamera milczy > 30 s, `ok` i `rec` = 0.

---

## 4× HX711 — tensometry zawieszenia ładunku (GPIO, RPi5 balon)

Każdy HX711 obsługuje jeden mostek tensometryczny. Cztery czujniki mierzą siłę
w narożnikach ramy zawieszenia ładunku (przód-lewy, przód-prawy, tył-lewy, tył-prawy).

| Kanał | Pozycja      | HX711 DT        | HX711 SCK       | VCC          | GND      |
|-------|--------------|-----------------|-----------------|--------------|----------|
| #0    | przód lewy   | GPIO16 (pin 36) | GPIO21 (pin 40) | 3.3V (pin 1) | GND      |
| #1    | przód prawy  | GPIO19 (pin 35) | GPIO20 (pin 38) | 3.3V (pin 1) | GND      |
| #2    | tył lewy     | GPIO12 (pin 32) | GPIO13 (pin 33) | 3.3V (pin 1) | GND      |
| #3    | tył prawy    | GPIO24 (pin 18) | GPIO25 (pin 22) | 3.3V (pin 1) | GND      |

> RPi5 (balon). ADC 24-bit, bit-banging przez `RPi.GPIO` — bez dodatkowej biblioteki.  
> `reference_unit` (ADC units/g) wymaga kalibracji z odważnikiem wzorcowym dla każdego kanału.  
> Klucze w JSON UART → ESP32: `"sg0"`, `"sg1"`, `"sg2"`, `"sg3"` [g].  
> Pola w telemetrii: `strain_g0` … `strain_g3`.

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
> Dane TX: temp, hum, pres (BME280), p2, alt2 (MS5611), roll, pit, yaw, ax, ay, az (BNO085), vbat, imA (INA219), dsku, dskf (dysk), hfdb (SDR dBFS, opcjonalne), sg0–sg3 (tensometry [g], opcjonalne), ec (status ESP32-CAM, opcjonalne).  
> Dane RX: komendy JSON od ESP32 — `{"cmd":"photo"}`, `{"cmd":"cam_rec","on":true/false}`, `{"cmd":"espcam_pwr","on":true/false}`, `{"cmd":"release_line","line":0|1|-1}`, shutdown request.

---

## Sygnały ESP32 ↔ RPi5 (GPIO)

| Sygnał         | RPi5 BCM          | ESP32 GPIO | Kierunek               |
|----------------|-------------------|------------|------------------------|
| RPI_ALIVE      | GPIO26 (pin 37)   | GPIO6      | RPi5 → ESP32           |
| ESP32_SHTDN    | GPIO6 (pin 31)    | GPIO7      | ESP32 → RPi5           |
| RPI_PWR        | —                 | GPIO5      | ESP32 → zasilanie RPi5 |

---

> **Nadzór zasilania (ESP32):** po włączeniu RPi ESP32 czeka na pierwszy stan wysoki ALIVE bez limitu czasu.
> Potem odcina zasilanie dopiero po 60 s ciągłego braku ALIVE (restart usługi nie gasi RPi), a po 30 min włącza je ponownie.
> Przy zamykaniu prąd znika 10 s po opadnięciu ALIVE, najpóźniej ~30 s od prośby o shutdown.
> `rpi-air/setup.sh` nadaje usłudze prawo do `sudo shutdown -h now` bez hasła.

## Beacon LoRa (ESP32 → ziemia)

Pakiet ma limit **255 B**, więc ESP32 nadaje krótkie klucze. Dekoduje je `rpi-ground/beacon.py` — zmieniaj oba pliki razem.

| Klucz | Zawartość |
|-------|-----------|
| `p`   | [lat, lon, alt, satelity, fix] |
| `vbe` | napięcie baterii z ADC ESP32 |
| `b`   | [vbat, imA] |
| `e`   | [temp, hum, pres, p2, alt2] |
| `i`   | [roll, pit, yaw, ax, ay, az] |
| `d`   | [dsku, dskf] |
| `h`   | hfdb |
| `c`   | status ESP32-CAM [ok, rec, klatki, wolne_MB] |
| `s`   | tensometry [sg0–sg3] |
| `x`   | 1 = część pól pominięta (kolejno d, s, i, c, h), bo pakiet był za długi |

---

## Tylko ESP32 (GPIO)

| Element     | ESP32 GPIO | Opis                                               |
|-------------|------------|----------------------------------------------------|
| Buzzer      | GPIO2      | alert audio (PWM 2800 Hz)                          |
| LED R       | GPIO17     | status (PWM)                                       |
| LED G       | GPIO18     | status (PWM)                                       |
| LED B       | GPIO20     | status (PWM)                                       |
| ADC baterii | GPIO1      | napięcie baterii (backup gdy RPi5 wyłączona)       |

---

## 2× HJR1-2C L-3VDC — przekaźniki systemu zwalniania linek (GPIO, RPi5 balon)

Model: **HJR1-2C L-3VDC** (cewka 3 V DC, ~70 mA, przełącznik 2C/DPDT).  
Każdy przekaźnik steruje jedną liną mocującą ładunek. Aktywacja przekaźnika przepala/zwalnia linkę i oddziela ładunek od balonu.

Cewka pobiera ~70 mA — zbyt dużo dla GPIO RPi5 (max 16 mA). Każdy kanał wymaga tranzystora NPN (np. 2N2222 / BC547) i diody zabezpieczającej cewkę (1N4007).

| Kanał    | RPi5 BCM          | Tranzystor base    | Rola                     |
|----------|-------------------|--------------------|--------------------------|
| Relay #0 | GPIO27 (pin 13)   | przez 100 Ω        | zwolnienie linki 0       |
| Relay #1 | GPIO5  (pin 29)   | przez 100 Ω        | zwolnienie linki 1       |

Schemat każdego kanału:
```
RPi GPIO ──[100Ω]──── Base (2N2222)
                       Emitter ──── GND
                       Collector ── Relay cewka (−)
3.3V ────────────────────────────── Relay cewka (+)
                       1N4007 (katoda → 3.3V, anoda → Collector)  ← ochrona przed back-EMF
Relay NO ──────────────────────────── mechanizm zwalniania linki
```

> RPi5 (balon). HIGH na GPIO = tranzystor otwarty = cewka aktywna = przekaźnik zamknięty = linka zwolniona.  
> Polecenie JSON (RPi5 ← ESP32 przez UART): `{"cmd":"release_line","line":0}` / `{"cmd":"release_line","line":1}`.  
> Obie linki jednocześnie: `{"cmd":"release_line","line":-1}`.  
> Po zwolnieniu GPIO wraca do LOW — cewka nie jest trzymana w sposób ciągły.  
> **UWAGA: `release_line` nie jest jeszcze zaimplementowane** w `rpi-air`, firmware ESP32 ani w backendzie — działa tylko test w `testy/`.

---

## Zajętość pinów GPIO — RPi5 balon

| Pin | BCM | Funkcja |
|-----|-----|---------|
| 3 / 5 | GPIO2 / GPIO3 | I2C: BME280, MS5611, BNO085, INA219 |
| 21 | GPIO9 | status ESP32-CAM (UART3 RX, 115200) |
| 24 | GPIO8 | UART3 TX (zarezerwowany, niepodłączony) |
| 8 / 10 | GPIO14 / GPIO15 | UART do ESP32-S3 |
| 13 | GPIO27 | przekaźnik #0 (zwolnienie linki) |
| 29 | GPIO5 | przekaźnik #1 (zwolnienie linki) |
| 31 | GPIO6 | ESP32_SHTDN (wejście) |
| 37 | GPIO26 | RPI_ALIVE (wyjście) |
| 36 / 40 | GPIO16 / GPIO21 | HX711 #0 (DT / SCK) |
| 35 / 38 | GPIO19 / GPIO20 | HX711 #1 (DT / SCK) |
| 32 / 33 | GPIO12 / GPIO13 | HX711 #2 (DT / SCK) |
| 18 / 22 | GPIO24 / GPIO25 | HX711 #3 (DT / SCK) |

Wolne po stronie balonu: GPIO4, GPIO7, GPIO10, GPIO11, GPIO17, GPIO18, GPIO22, GPIO23 (dawniej kanały kamer 1-3 — zwolnione po przejściu na jedną ESP32-CAM).

---

## Pułapki Raspberry Pi 5

- **RPi.GPIO nie działa na RPi 5.** Potrzebna nakładka lgpio:
  `sudo apt remove python3-rpi.gpio && sudo apt install python3-rpi-lgpio`.
  Dotyczy HX711, przekaźników i sygnałów do ESP32-S3.
  W `rpi-air/.venv` po `pip install -r requirements.txt` zrób też `pip uninstall -y RPi.GPIO`
  (dociąga je adafruit-blinka i przesłania rpi-lgpio).
- Status ESP32-CAM idzie przez sprzętowy UART3 (`dtoverlay=uart3-pi5` → `/dev/ttyAMA3`),
  bez pigpio (pigpio nie wspiera RPi 5).
- UART na RPi 5 to `/dev/ttyAMA0` (GPIO14/15) — w `raspi-config` wyłącz konsolę
  szeregową, a sam port zostaw włączony.
- SPI1 (nadajnik HF na stacji naziemnej) wymaga `dtoverlay=spi1-3cs`
  w `/boot/firmware/config.txt`.

---

## Sprawdzenie sprzętu przed startem

Cały ten dokument ma wersję klikalną: `python3 testy/main.py` uruchamia tester,
który dla każdego elementu pokazuje instrukcję podłączenia, podświetla jego piny
na rysunku złącza 40-pin i od razu wykonuje pomiar. Szczegóły w [testy/README.md](testy/README.md).
