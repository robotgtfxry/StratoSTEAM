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

# AD9833 (SPI1) — generator nośnej 144.800 MHz (eksperyment jonosferyczny)
# Czysta sinusoida, brak modulacji, brak kodowania pakietowego
# SDR na ziemi odbiera sygnał i mierzy opóźnienie odbicia
AD9833_SPI_BUS = 1
AD9833_SPI_CS = 2          # CE2 = GPIO16 (pin 36)
AD9833_CARRIER_FREQ = 144800000  # 144.800 MHz

# Buzzer i RGB LED — obsługiwane przez ESP32-S3 (zawsze zasilony)

# ESP32-S3 współpraca
RPI_ALIVE_PIN    = 26   # OUTPUT — RPi trzyma HIGH póki działa (pin 37 → ESP32 GPIO6)
ESP32_SHTDN_PIN  = 6    # INPUT  — ESP32 podnosi gdy chce shutdown (pin 31 ← ESP32 GPIO7)

# Nośna 144.800 MHz — czas trwania i interwał (eksperyment jonosferyczny)
CARRIER_DURATION_S = 5    # ile sekund nadajemy nośną
CARRIER_INTERVAL_S = 60   # co ile sekund włączamy nośną

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
CAM_RECORD_DIR     = "/home/pi/stratosteam-video"
CAM_PHOTO_W        = 160    # szerokość zdjęcia wysyłanego przez LoRa
CAM_PHOTO_H        = 120    # wysokość
CAM_PHOTO_QUALITY  = 25     # jakość JPEG (1-95); niższa = mniejszy plik = mniej chunków
CAM_CHUNK_INTERVAL_S = 3.0  # przerwa między wysłaniem kolejnych chunków do ESP32
