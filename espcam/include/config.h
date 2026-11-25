// StratoSTEAM — ESP32-CAM konfiguracja
// Na balonie pracuje jedna kamera ESP32-CAM: pio run -t upload

#pragma once

// ─── Katalog nagrań na karcie SD ─────────────────────────────────────────────
// Każdy start tworzy nowy katalog sesji: /CAM/S000, /CAM/S001, …
#define SESSION_ROOT         "/CAM"

// ─── Nagrywanie MJPEG AVI ────────────────────────────────────────────────────
// Czujnik na tej płytce: OV3660 (PID 0x3660). Pinout taki sam jak dla OV2640.
// VGA (640×480) @ 10fps @ quality 10 → ~100 KB/s → ~7 GB / 8h → karta 32 GB
#define FRAMESIZE            FRAMESIZE_VGA   // 640×480
#define CAM_WIDTH            640
#define CAM_HEIGHT           480
#define TARGET_FPS           10
#define CAPTURE_INTERVAL_MS  100             // 1000ms / TARGET_FPS
#define JPEG_QUALITY         10              // 0=najlepsza, 63=najgorsza

// Podział pliku co FILE_SPLIT_S sekund
// Przy utracie zasilania tracisz max jeden segment
#define FILE_SPLIT_S         300             // 5 minut na plik

// ─── Status UART → RPi ───────────────────────────────────────────────────────
// Idzie kablem USB: U0TX → CH340 (nakładka ESP32-CAM-MB) → USB RPi5
// Linie statusu zaczynają się od "$S" — RPi ignoruje pozostałe (debug, boot)
#define SERIAL_BAUD          115200
#define STATUS_INTERVAL_MS   5000

// ─── Zegar kamery ────────────────────────────────────────────────────────────
#define XCLK_FREQ_HZ         20000000

// ─── LED statusu ─────────────────────────────────────────────────────────────
// GPIO33 = mała czerwona dioda z tyłu płytki (LOW = świeci).
// NIE używać GPIO4 — to jasna lampa błyskowa (HIGH = świeci, ~200 mA).
#define LED_PIN              33
#define LED_ACTIVE           LOW
#define FLASH_PIN            4     // trzymana na LOW = lampa zgaszona
