# StratoSTEAM - Air node configuration (Raspberry Pi 5 on balloon)
# Architektura: RPi5 = czujniki + APRS | ESP32 = GPS + LoRa

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

# AD9833 (SPI1) - APRS beacon generator (144.800 MHz, odbierany osobnym SDR)
AD9833_SPI_BUS = 1
AD9833_SPI_CS = 2          # CE2 = GPIO16 (pin 36)
AD9833_APRS_FREQ = 144800000
APRS_CALLSIGN = "SP0STR-11"    # zmień na swój znak

# Buzzer i RGB LED — obsługiwane przez ESP32-S3 (zawsze zasilony)

# ESP32-S3 współpraca
RPI_ALIVE_PIN    = 26   # OUTPUT — RPi trzyma HIGH póki działa (pin 37 → ESP32 GPIO6)
ESP32_SHTDN_PIN  = 6    # INPUT  — ESP32 podnosi gdy chce shutdown (pin 31 ← ESP32 GPIO7)

# APRS beacon duration (ile sekund nadajemy nośną)
APRS_BEACON_DURATION_S = 5

# Uplink RX window — after each APRS TX, balon listens for commands this long
UPLINK_RX_WINDOW_S = 2.0

# APRS
APRS_BEACON_INTERVAL_S = 60    # APRS position beacon interval

# Camera (RPi cam0)
CAM_RECORD_DIR     = "/home/pi/stratosteam-video"
CAM_PHOTO_W        = 160    # szerokość zdjęcia wysyłanego przez LoRa
CAM_PHOTO_H        = 120    # wysokość
CAM_PHOTO_QUALITY  = 25     # jakość JPEG (1-95); niższa = mniejszy plik = mniej chunków
CAM_CHUNK_INTERVAL_S = 3.0  # przerwa między wysłaniem kolejnych chunków do ESP32
