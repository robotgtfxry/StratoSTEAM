# testy — tester czujników StratoSTEAM

Okienkowy program (tkinter), który po kolei sprawdza **cały sprzęt misji** i przy każdym
elemencie pokazuje, **jak go podłączyć do Raspberry Pi 5**: instrukcję krok po kroku,
tabelę połączeń i rysunek złącza 40-pin z podświetlonymi pinami.

Pomyślany tak, żeby uczeń mógł usiąść przed Raspberry Pi, wybrać czujnik z listy,
podłączyć go według rysunku i od razu kliknąć „Testuj”.

---

## Uruchomienie

Na Raspberry Pi 5 (z podłączonym monitorem albo przez VNC):

```bash
sudo apt install python3-tk
python3 testy/main.py
```

Na zwykłym komputerze, żeby zobaczyć jak program wygląda i działa (odczyty są udawane):

```bash
python3 testy/main.py --sim
```

Przez SSH, bez okna:

```bash
python3 testy/main.py --konsola        # wszystkie bezpieczne testy
python3 testy/main.py --test bme280    # jeden element
python3 testy/main.py --lista          # spis sprzętu i identyfikatorów
```

Biblioteki do konkretnych czujników: `testy/requirements.txt`. Nie trzeba instalować
wszystkiego naraz — brakującą bibliotekę test zgłosi razem z komendą do wpisania.

---

## Jak czytać wyniki

| Status              | Znaczenie                                                        |
|---------------------|------------------------------------------------------------------|
| **DZIAŁA**          | Czujnik odpowiada, a wartości mieszczą się w sensownym zakresie.  |
| **UWAGA**           | Odpowiada, ale coś jest podejrzane (np. brak fixa GPS, prąd = 0). |
| **BŁĄD**            | Brak komunikacji — przy wyniku jest lista rzeczy do sprawdzenia.  |
| **BRAK BIBLIOTEKI** | Sprzęt może być dobry, brakuje pakietu w systemie.                |
| **SPRAWDŹ RĘCZNIE** | Test wykonał akcję, ale ocenić musi człowiek (przekaźnik, HF).    |

Przycisk **Zapisz raport** zrzuca wszystkie wyniki do pliku `testy/raport-<data>.txt` —
wygodne przed startem misji.

---

## Co jest testowane

**Raspberry Pi 5 — balon**

| Element | Czym jest sprawdzany |
|---|---|
| Magistrala I2C | skan adresów, jak `i2cdetect` |
| BME280 | temperatura / wilgotność / ciśnienie + kontrola zakresu |
| MS5611 | ciśnienie i wysokość barometryczna |
| BNO085 | orientacja + kontrola, czy akcelerometr widzi 1 g |
| INA219 | napięcie, prąd, moc na baterii |
| HX711 ×4 | surowe odczyty ADC, wykrycie zerwanego mostka i szumu |
| Kamera CSI | zdjęcie próbne 640×480 + kontrola czy nie jest czarne |
| RTL-SDR | otwarcie dongla i pomiar mocy nośnej w dBFS |
| ESP32-CAM (zasilanie) | przełączanie MOSFET-a na GPIO17 |
| ESP32-CAM (status) | odbiór linii JSON `$S` po UART (GPIO4) |
| UART ↔ ESP32-S3 | nasłuch łącza + ping |
| Sygnały GPIO ↔ ESP32-S3 | RPI_ALIVE i linia shutdown |
| Przekaźniki ×2 | impuls zwalniający linki — **z potwierdzeniem** |

**Raspberry Pi 5 — stacja naziemna**

| Element | Czym jest sprawdzany |
|---|---|
| LoRa SX1278 | rejestr wersji przez SPI (musi być 0x12) |
| LoRa — nasłuch | 12 s oczekiwania na pakiet, RSSI i SNR |
| AD9833 + RD06HHF1 | ustawienie generatora — **bez kluczowania PTT** |

**Moduły ESP32 — test na stole**

| Element | Czym jest sprawdzany |
|---|---|
| GPS NEO-M8N | zdania NMEA, liczba satelitów, fix |

---

## Bezpieczeństwo

Dwa testy wykonują fizyczne akcje i przed uruchomieniem pytają o potwierdzenie:

* **Przekaźniki zwalniania linek** — przed testem zdejmij linki z mechanizmu,
  inaczej ładunek zostanie zwolniony.
* **Nadajnik HF** — test tylko zapisuje rejestry AD9833, PTT zostaje w stanie niskim
  (brak emisji). Do prawdziwego nadawania potrzebne są uprawnienia krótkofalarskie
  i podłączona antena albo sztuczne obciążenie.

Oba testy są pomijane przez „Testuj wszystko” i przez tryb `--konsola`.

---

## Skąd tester bierze dane

Nic nie jest tu przepisane „na drugą stronę”. Tester wczytuje **te same pliki, które lecą
na balonie**:

* sterowniki: `rpi-air/sensors/*.py`, `rpi-air/hardware/*.py`,
* konfiguracje: `rpi-air/config.py`, `rpi-ground/config.py` (adresy I2C, piny, prędkości).

Zmiana pinu w `config.py` od razu zmienia instrukcję podłączenia w okienku.
Opisy podłączeń są zebrane w jednym miejscu — `testy/catalog.py`.

---

## Pliki

| Plik | Rola |
|---|---|
| `main.py` | uruchamianie: GUI, `--sim`, `--konsola`, `--lista`, `--test` |
| `gui.py` | okno tkinter, rysunek złącza 40-pin |
| `catalog.py` | katalog sprzętu: opisy, instrukcje, tabele połączeń |
| `hw_tests.py` | same testy — każdy zwraca status, wartości i podpowiedzi |
| `pinout.py` | mapa 40-pinowego złącza Raspberry Pi 5 |
| `repo.py` | ładowanie sterowników i konfiguracji z reszty repozytorium |

---

## Znane pułapki Raspberry Pi 5

* **RPi.GPIO** nie działa na RPi 5 — potrzebna podmianka:
  `sudo apt remove python3-rpi.gpio && sudo apt install python3-rpi-lgpio`.
  Dotyczy HX711, przekaźników, zasilania ESP32-CAM i sygnałów do ESP32-S3.
* **pigpio** nie wspiera RPi 5 — odczyt statusu ESP32-CAM (bit-bang serial) trzeba będzie
  przepisać na `lgpio` albo na sprzętowy UART. Test to wykryje i napisze wprost.
* Usługa `stratosteam-air` zajmuje UART i kamerę. Przed testami:
  `sudo systemctl stop stratosteam-air`.
