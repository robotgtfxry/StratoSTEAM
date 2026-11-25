# Hardware — mapa czujników

> **Architektura systemu:**
> - **ESP32-S3 (balon)** — węzeł radiowy: GPS (NEO-M8N) + LoRa (SX1278), retransmisja danych z RPi5
> - **Raspberry Pi 5 (balon)** — węzeł pomiarowy: czujniki atmosferyczne, IMU, kamera CSI, 1× ESP32-CAM (zasilanie + status po USB), RTL-SDR (odbiór sygnału HF z ziemi), 2× przekaźnik HJR1-2C L-3VDC (system zwalniania linek)
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

## LoRa SX1278 — stacja naziemna 433 MHz (SPI0, RPi5 ziemia)

| Pin LoRa | RPi5 BCM            | Pin fizyczny    |
|----------|---------------------|-----------------|
| VCC      | 3.3V                | pin 17 (lub 1)  |
| GND      | GND                 | pin 20 (lub 25) |
| SCK      | GPIO11 (SPI0 SCLK)  | pin 23          |
| MOSI     | GPIO10 (SPI0 MOSI)  | pin 19          |
| MISO     | GPIO9 (SPI0 MISO)   | pin 21          |
| NSS/CS   | GPIO8 (SPI0 CE0)    | pin 24          |
| DIO0     | GPIO25              | pin 22          |
| RST      | niepodłączony / 3.3V | —              |

> RPi5 (ziemia). Piny w `rpi-ground/config.py`: `LORA_SPI_BUS = 0`, `LORA_SPI_CS = 0`, `LORA_DIO0_PIN = 25`.  
> **Tylko 3.3V** — 5V uszkodzi moduł.  
> **Antena 433 MHz musi być podłączona przed startem** — stacja nadaje uplink 17 dBm (PA_BOOST), TX bez anteny może uszkodzić tor PA.  
> RST nie jest sterowany przez `rpi-ground/radio/lora_rx.py` (wewnętrzny pull-up) — można zostawić wolny.  
> Brak konfliktu z AD9833 (SPI1, GPIO18–21) ani PTT (GPIO24).

**Włączenie SPI:**
```bash
sudo raspi-config nonint do_spi 0
echo "dtoverlay=spi1-2cs" | sudo tee -a /boot/firmware/config.txt   # SPI1 dla AD9833
sudo reboot
```
Po restarcie: `/dev/spidev0.0` (LoRa) i `/dev/spidev1.1` (AD9833).

**Test połączenia** (rejestr `RegVersion` 0x42):
```bash
python3 -c "
import spidev; s=spidev.SpiDev(); s.open(0,0); s.max_speed_hz=1000000
print(hex(s.xfer2([0x42,0])[1]))"
```
`0x12` = SX1278 OK. `0x0` / `0xff` = błąd okablowania (zamienione MISO/MOSI, zły CS, brak zasilania).

> Na RPi 5 `RPi.GPIO` nie działa — wymagany zamiennik `rpi-lgpio` (`pip install rpi-lgpio`).

---

## Kamera — RPi Camera Module (CSI cam0, RPi5 balon)

| Złącze | RPi5               |
|--------|--------------------|
| CSI    | CAM0 (15-pin, pin 1)|

> RPi5 (balon). Ciągłe nagrywanie H.264 Full HD (1920×1080, 25 kl./s, 4 Mbps) na dysk — katalog z `CAM_RECORD_DIR`. Parametry: `CAM_RECORD_*` w `rpi-air/config.py`.  
> Na żądanie z Flutter: zdjęcie 160×120 JPEG, chunki po 140 bajtów (base64), przesyłane przez UART → LoRa → backend.  
> Dysk monitorowany: `shutil.disk_usage()`, dane `dsku`/`dskf` w beaconie ESP32 (pole `d`).  
> 4 Mbps to ~1.8 GB na godzinę (~14 GB na 8 h lotu). 4K zjadało ok. 1.5 rdzenia i dawało tylko 14 kl./s.

---

## ESP32-CAM — podłączenie po USB do RPi5 (balon)

Na balonie leci **jedna** kamera ESP32-CAM (AI-Thinker, czujnik **OV3660**) w nakładce **ESP32-CAM-MB** (CH340).
Jeden kabel USB daje **zasilanie i status** — żadnych połączeń z GPIO.

```
 RPi5 USB ═══ kabel USB (z liniami danych) ═══ ESP32-CAM-MB + ESP32-CAM
```

W `rpi-air/config.py`: `ESPCAM_UART_PORT = "auto"`, `ESPCAM_PWR_PIN = None`.

- Port jest wyszukiwany po układzie CH340, więc numer `ttyUSB` nie ma znaczenia. Kabel można wypiąć i wpiąć — odczyt wraca sam.
- Przy **dwóch** CH340 na USB wpisz stałą ścieżkę z `ls -l /dev/serial/by-path/`. Program celowo nie zgaduje: otwarcie portu ESP32-S3 mogłoby go zresetować i odciąć zasilanie RPi.
- Start usługi `rpi-air` może raz zrestartować kamerę — zaczyna wtedy nową sesję nagrań.
- Sprawdzenie: `lsusb | grep 1a86`, potem `python3 testy/main.py --test espcam_status`.
- Po zmianie z UART3 uruchom raz `sudo bash rpi-air/setup.sh` i zrób reboot.

> Komenda LoRa `espcam_pwr` jest ignorowana (tylko log). Żeby wrócić do przełączania MOSFET-em: ustaw `ESPCAM_PWR_PIN` na numer GPIO (np. 17) i użyj tranzystora logic-level ≥1 A (AO3400 / IRLZ44N — nie BSS138, za słaby).

### Oprogramowanie ESP32-CAM (`espcam/src/main.cpp`)

- Ciągle nagrywa MJPEG AVI (VGA 640×480, ~9.5 fps, `JPEG_QUALITY 10`) na kartę SD
- Dzieli plik co `FILE_SPLIT_S` (5 min) — przy utracie zasilania tracisz maksymalnie jeden segment
- Przy każdym starcie tworzy nowy katalog sesji: `/CAM/S000`, `/CAM/S001`, …
- Bez karty SD kamera działa dalej i co 30 s sprawdza, czy karta się pojawiła — wtedy sama zaczyna nagrywać
- Karta: **FAT32, ≤ 32 GB** (SDHC)
- **Bez WiFi** — tylko zapis na SD
- LED statusu: mała czerwona dioda **GPIO33** (z tyłu płytki), co 2 s: 1× = OK, 2× = brak SD, 3× = błąd kamery. Lampa błyskowa GPIO4 jest zawsze zgaszona.

**Wgrywanie:** `cd espcam && pio run -t upload` (przez nakładkę ESP32-CAM-MB / USB)

**Status przez USB** — co 5 s linia z prefiksem `$S`:
```
$S{"ok":1,"rec":1,"sd":1,"n":1234,"mb":7800,"fps":9.5}
```
`ok` = kamera działa, `rec` = trwa zapis, `sd` = karta zamontowana, `n` = klatki, `mb` = wolne MB, `fps` = klatki/s.
Linie bez `$S` (boot, debug) są ignorowane. `EspCamMonitor` (pyserial, USB) dokłada `"ec": [ok, rec, klatki, wolne_MB]` do pakietu UART → ESP32-S3 → LoRa (pole `c`) → backend → Flutter. Gdy kamera milczy > 30 s, `ok` i `rec` = 0.

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

## Czujniki: GY-87 + INA226 (zamontowane) zamiast wersji z PCB

Na balonie są fizycznie: BME280 (0x76), MPU-6050 (0x68), BMP180 (0x77), INA226 (0x44).
Wybiera je `SENSOR_SET = "gy87"` w `rpi-air/config.py`; `"pcb"` = BNO085 + MS5611 + INA219.

> BMP180 i BME280 mierzą tylko do 300 hPa (~9 km) — wyżej wysokość bierz z GPS.
> Yaw = 0: kompas z GY-87 nie jest jeszcze obsługiwany.

---

## Tor HF — DO ZROBIENIA (wyłączony)

> **Nie leci w tej wersji:** brakuje jednego filtra. Kod zostaje, ale jest wyłączony:
> `HF_ENABLED = False` (`rpi-ground/config.py`), `SDR_ENABLED = False` (`rpi-air/config.py`),
> `HfService.enabled` (Flutter — domyślnie `false`, włączenie: `flutter build apk --dart-define=HF_ENABLED=true`).
> Miejsca w kodzie: `grep -rn "TODO(HF)"`.

Do zrobienia przed włączeniem:

- [ ] dokupić i wlutować brakujący filtr
- [ ] direct sampling w `sdr_receiver.py` (zwykły RTL-SDR nie stroi się na 7.1 MHz) albo RTL-SDR V4 ze sterownikiem RTL-SDR Blog
- [ ] `SDR_GAIN` na stałą wartość — przy `auto` pomiarów z różnych wysokości nie da się porównać
- [ ] szersze okno FFT — ±15 binów to ok. ±15 Hz, błąd kwarcu bywa większy
- [ ] automatyczne wyłączenie nadajnika po utracie łączności z backendem (`hf_controller.py`)
- [ ] licencja / pozwolenie na nadawanie w paśmie 40 m

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

> **Łącze po USB (używane):** kabel USB RPi5 → port „UART/COM” płytki ESP32-S3 (CH343) przenosi to samo co przewody
> poniżej. Program sam wybiera USB, a gdy kabla nie ma — przewody (`ESP_USB_ENABLED` w `rpi-air/config.py`).
> **Do lotu S3 musi mieć własne 5V**, inaczej zgaśnie razem z RPi. W kablu USB trzeba wtedy przerwać żyłę 5V
> (czerwoną), zostawić GND, D+ i D−. Nie otwieraj tego portu innym programem, gdy działa `rpi-air`.

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
| 8 / 10 | GPIO14 / GPIO15 | UART do ESP32-S3 |
| 13 | GPIO27 | przekaźnik #0 (zwolnienie linki) |
| 29 | GPIO5 | przekaźnik #1 (zwolnienie linki) |
| 31 | GPIO6 | ESP32_SHTDN (wejście) |
| 37 | GPIO26 | RPI_ALIVE (wyjście) |
| 36 / 40 | GPIO16 / GPIO21 | HX711 #0 (DT / SCK) |
| 35 / 38 | GPIO19 / GPIO20 | HX711 #1 (DT / SCK) |
| 32 / 33 | GPIO12 / GPIO13 | HX711 #2 (DT / SCK) |
| 18 / 22 | GPIO24 / GPIO25 | HX711 #3 (DT / SCK) |

Wolne po stronie balonu: GPIO4, GPIO7, GPIO8, GPIO9, GPIO10, GPIO11, GPIO17, GPIO18, GPIO22, GPIO23 (dawniej kanały kamer 1-3 — zwolnione po przejściu na jedną ESP32-CAM).

---

## Pułapki Raspberry Pi 5

- **RPi.GPIO nie działa na RPi 5.** Potrzebna nakładka lgpio:
  `sudo apt remove python3-rpi.gpio && sudo apt install python3-rpi-lgpio`.
  Dotyczy HX711, przekaźników i sygnałów do ESP32-S3.
  W `rpi-air/.venv` po `pip install -r requirements.txt` zrób też `pip uninstall -y RPi.GPIO`
  (dociąga je adafruit-blinka i przesłania rpi-lgpio).
- Status ESP32-CAM idzie kablem USB (CH340) — port wyszukiwany automatycznie.
- UART na RPi 5 to `/dev/ttyAMA0` (GPIO14/15) — w `raspi-config` wyłącz konsolę
  szeregową, a sam port zostaw włączony.
- SPI1 (nadajnik HF na stacji naziemnej) wymaga `dtoverlay=spi1-3cs`
  w `/boot/firmware/config.txt`.

---

## Sprawdzenie sprzętu przed startem

Cały ten dokument ma wersję klikalną: `python3 testy/main.py` uruchamia tester,
który dla każdego elementu pokazuje instrukcję podłączenia, podświetla jego piny
na rysunku złącza 40-pin i od razu wykonuje pomiar. Szczegóły w [testy/README.md](testy/README.md).
