# StratoSTEAM — aplikacja operatora (Flutter)

Aplikacja mobilna stacji naziemnej: pokazuje telemetrię z balonu i pozwala wysyłać
komendy w górę. Rozmawia wyłącznie z backendem (`backend/`), nigdy bezpośrednio
z radiem — droga komendy to:

```
Flutter → backend (HTTP) → rpi-ground (polling) → LoRa → ESP32-S3 → UART → RPi5
```

## Uruchomienie

```bash
flutter pub get
flutter run
```

Adres serwera i klucz API ustawia się w aplikacji (ekran Ustawienia) — domyślnie
`http://localhost:8000`. Backend musi być uruchomiony (`uvicorn main:app` w `backend/`).

Build APK:

```bash
flutter build apk --release
```

## Co pokazuje

| Panel | Zawartość |
|---|---|
| Telemetria | temperatura, wilgotność, ciśnienie, wysokość (MS5611 i GPS), napięcie i prąd baterii |
| Orientacja | roll / pitch / yaw z BNO085 |
| Mapa | pozycja z GPS, ślad lotu |
| Tensometry | siła w 4 narożnikach zawieszenia (HX711) |
| Kamera RPi | ostatnie zdjęcie 160×120 przesłane przez LoRa, żądanie nowego, start/stop nagrywania 4K |
| ESP32-CAM | włącznik zasilania jedynej kamery + status: nagrywa / klatki / wolne MB na karcie |
| Zasilanie RPi | włączenie i bezpieczne wyłączenie RPi na balonie (przez ESP32-S3) |
| Nadajnik HF | start/stop i częstotliwość generatora AD9833 na stacji naziemnej |
| Wykres HF | siła sygnału (dBFS) zmierzona przez RTL-SDR w funkcji wysokości |
| Zwalnianie linek | komenda odczepienia ładunku od balonu |

Komendy zmieniające stan sprzętu wymagają PIN-u (`pin_dialog.dart`) — chroni to
przed przypadkowym kliknięciem w locie.

## Struktura

| Katalog | Rola |
|---|---|
| `lib/screens/` | ekrany: dashboard, mapa, ustawienia |
| `lib/widgets/` | karty paneli (telemetria, kamery, zasilanie, HF) |
| `lib/services/` | klienci HTTP backendu, każdy jako `ChangeNotifier` |

Stan aplikacji trzyma `provider` — serwisy odpytują backend w tle (co 5–10 s)
i powiadamiają widżety o zmianach.

## Powiązane dokumenty

* [../HARDWARE.md](../HARDWARE.md) — mapa czujników i połączeń
* [../testy/README.md](../testy/README.md) — tester sprzętu przed startem
