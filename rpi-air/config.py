# StratoSTEAM - Air node configuration (Raspberry Pi 5 on balloon)
# Architektura: RPi5 = czujniki + nośna 144.800 MHz | ESP32 = GPS + LoRa

# UART do ESP32 (RPi5 GPIO14 TX → ESP32 GPIO3 RX)
ESP_UART_PORT = "/dev/ttyAMA0"
ESP_UART_BAUD = 115200
# Kabel USB do ESP32-S3 (układ CH343) ma pierwszeństwo; gdy go nie ma — przewody UART powyżej.
ESP_USB_ENABLED = True
ESP_SEND_INTERVAL_S = 5     # jak często wysyłamy dane czujników do ESP32

# BME280 (I2C)
BME280_ADDR = 0x76

# Zestaw czujników zamontowany na balonie:
#   "gy87" = GY-87 (MPU-6050 + BMP180) i INA226 — to, co jest fizycznie podłączone
#   "pcb"  = BNO085 + MS5611 + INA219 — wersja z płytki PCB
SENSOR_SET = "gy87"

# GY-87 + INA226 (I2C)
MPU6050_ADDR = 0x68
BMP180_ADDR = 0x77
INA226_ADDR = 0x44
INA226_SHUNT_OHMS = 0.1     # wartość bocznika na module — sprawdź nadruk (R100 = 0.1)

# MS5611 (I2C)
MS5611_ADDR = 0x77

# BNO085 (I2C)
BNO085_ADDR = 0x4A

# INA219 (I2C) - battery monitor
INA219_ADDR = 0x40
INA219_SHUNT_OHMS = 0.1

# ESP32-CAM — 1 kamera, podłączona kablem USB do RPi (nakładka ESP32-CAM-MB).
# USB daje zasilanie i status, kamera jest zawsze włączona — nic więcej nie trzeba.
# None = brak przełączania zasilania. Jeśli kiedyś wróci MOSFET: numer GPIO BCM (np. 17).
ESPCAM_PWR_PIN = None

# "auto" = znajdź kamerę po układzie CH340 (niezależnie od numeru ttyUSB).
# Gdy podłączone są dwa CH340 — wpisz stałą ścieżkę z: ls -l /dev/serial/by-path/
ESPCAM_UART_PORT = "auto"
ESPCAM_STATUS_BAUD = 115200  # musi zgadzać się z SERIAL_BAUD w espcam/include/config.h

# Buzzer i RGB LED — obsługiwane przez ESP32-S3 (zawsze zasilony)

# ESP32-S3 współpraca
RPI_ALIVE_PIN    = 26   # OUTPUT — RPi trzyma HIGH póki działa (pin 37 → ESP32 GPIO6)
ESP32_SHTDN_PIN  = 6    # INPUT  — ESP32 podnosi gdy chce shutdown (pin 31 ← ESP32 GPIO7)

# RTL-SDR odbiornik HF (eksperyment jonosferyczny)
# TODO(HF): DO ZROBIENIA — wyłączone, brakuje jednego filtra w torze HF.
#           Lista rzeczy do zrobienia przed włączeniem: HARDWARE.md → „Tor HF”.
#           Włączać razem z HF_ENABLED w rpi-ground/config.py i w Flutterze (hf_service.dart).
SDR_ENABLED          = False
SDR_TARGET_FREQ      = 7_100_000   # Hz — musi zgadzać się z nadajnikiem naziemnym
SDR_SAMPLE_RATE      = 250_000     # Hz
SDR_GAIN             = "auto"      # lub np. 40 (dB)
SDR_FREQ_CORRECTION  = 0           # PPM korekcja kwarcu RTL-SDR
SDR_MEASURE_INTERVAL_S = 10        # co ile sekund mierzymy
SDR_NUM_SAMPLES      = 256 * 1024  # próbki na pomiar (~1 s)
SDR_BIN_WINDOW       = 15          # ±bin wokół nośnej w FFT

# Camera (RPi cam0)
CAM_RECORD_DIR     = "/home/admin/stratosteam-video"
# Film w kawałkach — nagłe odcięcie zasilania psuje najwyżej ostatni kawałek
CAM_SEGMENT_S      = 600
# Poniżej tylu GB wolnego film się wstrzymuje, żeby dziennik lotu miał miejsce
CAM_MIN_FREE_GB    = 1.0
# Full HD zamiast 4K — dużo mniejszy pobór mocy (RPi 5 koduje H.264 procesorem)
CAM_RECORD_W       = 1920
CAM_RECORD_H       = 1080
CAM_RECORD_FPS     = 25
CAM_RECORD_BITRATE = 4_000_000   # bit/s → ~1.8 GB na godzinę
# Zdjęcie przez LoRa: (szerokość, wysokość, maks. bajtów) zależnie od SF, które wybrała ziemia.
# Czas serii ok.: SF7 25 s, SF8 25 s, SF9 30 s, SF10 45 s.
CAM_PHOTO_BY_SF = {
    7:  (640, 360, 13500),
    8:  (480, 270, 7200),
    9:  (400, 225, 4800),
    10: (320, 180, 3600),
}
# Istnieje w trakcie lotu (komenda START ze stacji) → ostrość na stałe na nieskończoność.
# Bez niego działa autofokus. Plik, żeby restart RPi w locie tego nie zmienił.
FLIGHT_FLAG        = "/home/admin/.stratosteam-lot"

# Dziennik lotu na karcie (CSV + JSONL) — wszystko, także bez łączności z ziemią
FLIGHT_LOG_DIR     = "/home/admin/stratosteam-logi"
LOG_INTERVAL_S     = 1
PREVIEW_PORT       = 8081   # podgląd na żywo po sieci (tylko Tailscale), None = wyłączony
