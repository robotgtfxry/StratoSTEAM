// StratoSTEAM — ESP32-CAM konfiguracja
// PlatformIO: indeks ustawiany przez środowisko (pio run -e cam0/cam1/cam2/cam3)
// Arduino IDE: zmień CAM_INDEX ręcznie przed wgraniem

#pragma once

// ─── Identyfikator kamery (0-3) ───────────────────────────────────────────────
#ifndef CAM_INDEX
#define CAM_INDEX 0
#endif

// ─── Nagrywanie MJPEG AVI ────────────────────────────────────────────────────
// OV2640 stabilnie daje ~10 fps przy VGA
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
// ESP32-CAM GPIO1 (U0TX) → RPi GPIO (bit-bang, 115200 baud)
// Linie statusu zaczynają się od "$S" — RPi ignoruje pozostałe (debug, boot)
#define SERIAL_BAUD          115200
#define STATUS_INTERVAL_MS   5000

// ─── LED statusu ─────────────────────────────────────────────────────────────
#define LED_PIN              4     // wbudowana lampa błyskowa AI-Thinker
#define LED_ACTIVE           LOW   // LOW = ON
