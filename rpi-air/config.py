# StratoSTEAM - Air node configuration (Raspberry Pi 5 on balloon)
# Architektura: RPi5 = czujniki + nośna 144.800 MHz | ESP32 = GPS + LoRa

# UART do ESP32 (RPi5 GPIO14 TX → ESP32 GPIO3 RX)
ESP_UART_PORT = "/dev/ttyAMA0"
ESP_UART_BAUD = 115200
ESP_SEND_INTERVAL_S = 5     # jak często wysyłamy dane czujników do ESP32

# BME280 (I2C)
BME280_ADDR = 0x76

# MS5611 (I2C)
MS5611_ADDR = 0x77

# BNO085 (I2C)
BNO085_ADDR = 0x4A

# INA219 (I2C) - battery monitor
INA219_ADDR = 0x40
INA219_SHUNT_OHMS = 0.1

# ESP32-CAM — 1 kamera, zasilanie przełączane przez MOSFET (low-side, GPIO → gate 100Ω)
ESPCAM_PWR_PIN = 17          # GPIO BCM (pin 11) — HIGH = kamera zasilona

# ESP32-CAM — odczyt statusu przez UART (bit-bang pigpio)
# ESP32-CAM GPIO1 (U0TX) → RPi GPIO poniżej
# Poziomy napięć zgodne: ESP32-CAM 3.3V = RPi 3.3V (bez level-shiftera)
ESPCAM_STATUS_PIN = 4        # GPIO BCM (pin 7)
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
SDR_ENABLED          = True
SDR_TARGET_FREQ      = 7_100_000   # Hz — musi zgadzać się z nadajnikiem naziemnym
SDR_SAMPLE_RATE      = 250_000     # Hz
SDR_GAIN             = "auto"      # lub np. 40 (dB)
SDR_FREQ_CORRECTION  = 0           # PPM korekcja kwarcu RTL-SDR
SDR_MEASURE_INTERVAL_S = 10        # co ile sekund mierzymy
SDR_NUM_SAMPLES      = 256 * 1024  # próbki na pomiar (~1 s)
SDR_BIN_WINDOW       = 15          # ±bin wokół nośnej w FFT

# Camera (RPi cam0)
CAM_RECORD_DIR     = "/home/admin/stratosteam-video"
CAM_PHOTO_W        = 160    # szerokość zdjęcia wysyłanego przez LoRa
CAM_PHOTO_H        = 120    # wysokość
CAM_PHOTO_QUALITY  = 25     # jakość JPEG (1-95); niższa = mniejszy plik = mniej chunków
CAM_CHUNK_INTERVAL_S = 3.0  # przerwa między wysłaniem kolejnych chunków do ESP32
