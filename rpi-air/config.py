# StratoSTEAM - Air node configuration (Raspberry Pi 5 on balloon)

# LoRa SX1278 (SPI)
LORA_FREQ = 433.0          # MHz
LORA_SF = 10               # Spreading Factor (range vs speed tradeoff)
LORA_BW = 125000           # Bandwidth Hz
LORA_CR = 5                # Coding rate 4/5
LORA_TX_POWER = 17         # dBm
LORA_SPI_BUS = 0
LORA_SPI_CS = 0
LORA_DIO0_PIN = 25         # BCM GPIO

# NEO-M8N GPS (UART)
GPS_PORT = "/dev/ttyAMA0"
GPS_BAUD = 9600

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

# Uplink RX window — after each TX, balon listens for commands this long
UPLINK_RX_WINDOW_S = 2.0

# Telemetry
TELEMETRY_INTERVAL_S = 5       # how often to send packet
APRS_BEACON_INTERVAL_S = 60    # APRS position beacon interval
