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
| Magistrala I2C | skan adresów jak `i2cdetect` + rozpoznanie układu po rejestrze ID |
| BME280 | temperatura / wilgotność / ciśnienie + kontrola zakresu |
| GY-87: MPU-6050 | akcelerometr i żyroskop, kontrola czy widzi 1 g, roll / pitch |
| GY-87: QMC5883L / HMC5883L | pole magnetyczne, natężenie, kierunek kompasu |
| GY-87: BMP180 | ciśnienie, temperatura, wysokość barometryczna |
| INA226 | napięcie, prąd, moc na baterii (ID producenta 0x5449) |
| Kamera CSI | zdjęcie próbne 640×480 + kontrola czy nie jest czarne |
| RTL-SDR | otwarcie dongla i pomiar mocy nośnej w dBFS |
| ESP32-CAM (zasilanie) | stałe z USB — test tylko informuje |
| ESP32-CAM (status) | odbiór linii JSON `$S` po USB (CH340, port wyszukiwany automatycznie) |
| UART ↔ ESP32-S3 | nasłuch łącza + ping |
| Sygnały GPIO ↔ ESP32-S3 | RPI_ALIVE i linia shutdown |
| Przekaźniki ×2 | impuls zwalniający linki — **z potwierdzeniem** |

**Moduły ESP32-S3 — test na stole**

| Element | Czym jest sprawdzany |
|---|---|
| GPS NEO-M8N | zdania NMEA, liczba satelitów, fix |

LoRa SX1278 siedzi na ESP32-S3, więc z Raspberry Pi nie da się jej sprawdzić bezpośrednio —
działające łącze widać po teście UART ↔ ESP32-S3.

> Magnetometr GY-87 jest podpięty za MPU-6050 i pojawia się w skanie I2C dopiero po
> teście MPU-6050 albo magnetometru (włączają bypass I2C w MPU).

---

## Bezpieczeństwo

Test **przekaźników zwalniania linek** wykonuje fizyczną akcję i przed uruchomieniem
pyta o potwierdzenie — przed testem zdejmij linki z mechanizmu, inaczej ładunek zostanie
zwolniony. Jest pomijany przez „Testuj wszystko” i przez tryb `--konsola`.

---

## Skąd tester bierze dane

Tam, gdzie lotny kod ma sterownik, tester wczytuje **te same pliki, które lecą na balonie**:

* sterowniki: `rpi-air/sensors/bme280.py`, `rpi-air/hardware/*.py` (kamera, RTL-SDR),
* konfiguracja: `rpi-air/config.py` (adresy I2C, piny, prędkości).

GY-87 i INA226 tester czyta bezpośrednio przez `smbus2` (`hw_tests.py`); kod lotny ma własne
sterowniki w `rpi-air/sensors/` (magnetometr QMC5883L/HMC5883L tylko w testerze).
Adresy i bocznik można nadpisać w `rpi-air/config.py`: `MPU6050_ADDR`, `BMP180_ADDR`,
`INA226_ADDR`, `INA226_SHUNT_OHMS`, a port statusu kamery: `ESPCAM_UART_PORT`.

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
| `repo.py` | ładowanie sterowników i konfiguracji z `rpi-air/` |

---

## Znane pułapki Raspberry Pi 5

* **RPi.GPIO** nie działa na RPi 5 — potrzebna podmianka:
  `sudo apt remove python3-rpi.gpio && sudo apt install python3-rpi-lgpio`.
  Dotyczy przekaźników, zasilania ESP32-CAM i sygnałów do ESP32-S3.
* **ESP32-CAM po USB**: kabel musi mieć linie danych, a pakiet `brltty` potrafi przejąć CH340
  (`setup.sh` w `rpi-air` go wyłącza).
* Usługa `rpi-air` zajmuje UART i kamerę. Przed testami:
  `sudo systemctl stop rpi-air`.
