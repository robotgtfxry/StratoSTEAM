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

# HX711 — 4× czujnik siły (tensometry, zawieszenie ładunku)
# Każdy HX711 na osobnych pinach GPIO (DT + SCK)
HX711_SENSORS = [
    {"dt": 16, "sck": 21},   # #0 — przód lewy  (GPIO16 pin36, GPIO21 pin40)
    {"dt": 19, "sck": 20},   # #1 — przód prawy (GPIO19 pin35, GPIO20 pin38)
    {"dt": 12, "sck": 13},   # #2 — tył lewy    (GPIO12 pin32, GPIO13 pin33)
    {"dt": 24, "sck": 25},   # #3 — tył prawy   (GPIO24 pin18, GPIO25 pin22)
]
HX711_REFERENCE_UNIT = 1.0   # ADC units per gram — wymaga kalibracji z odważnikiem

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
# Full HD zamiast 4K — dużo mniejszy pobór mocy (RPi 5 koduje H.264 procesorem)
CAM_RECORD_W       = 1920
CAM_RECORD_H       = 1080
CAM_RECORD_FPS     = 25
CAM_RECORD_BITRATE = 4_000_000   # bit/s → ~1.8 GB na godzinę
CAM_PHOTO_W        = 160    # szerokość zdjęcia wysyłanego przez LoRa
CAM_PHOTO_H        = 90     # wysokość (16:9 jak kamera)
CAM_PHOTO_QUALITY  = 25     # jakość JPEG (1-95); niższa = mniejszy plik = mniej chunków
# Fragment i beacon zajmują radio po ~2.1 s, beacon idzie co 5 s — częściej niż co 5 s
# fragmenty się nie mieszczą i giną.
CAM_CHUNK_INTERVAL_S = 5.0
CAM_CHUNK_REPEAT   = 2      # ile razy wysłać komplet fragmentów (drugi raz łata zgubione)
PREVIEW_PORT       = 8081   # podgląd na żywo po sieci (tylko Tailscale), None = wyłączony
