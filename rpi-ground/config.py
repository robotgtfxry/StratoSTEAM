# StratoSTEAM — Ground station configuration

# LoRa RX (must match air config exactly)
LORA_FREQ = 433.0
LORA_SF = 10
LORA_BW = 125000
LORA_CR = 5
LORA_SPI_BUS = 0
LORA_SPI_CS = 0
LORA_DIO0_PIN = 25

# Backend server
BACKEND_URL = "http://localhost:8000"          # local dev
# BACKEND_URL = "https://your-server.example.com"  # production
BACKEND_API_KEY = "change-me-in-production"

# How often to flush buffered packets when offline (seconds)
OFFLINE_FLUSH_INTERVAL_S = 10

# AD9833 + LPF-B0R35+ + RD06HHF1 — HF ionospheric test transmitter
AD9833_SPI_BUS = 1
AD9833_SPI_CS  = 1
AD9833_MCLK_HZ = 25_000_000     # 25 MHz crystal on AD9833 module
HF_PTT_PIN     = 24             # BCM GPIO — keys the RD06HHF1 via PTT line
HF_DEFAULT_FREQ_HZ = 7_100_000  # 7.1 MHz (40m band) as default test frequency
HF_POLL_INTERVAL_S = 1.0        # how often rpi-ground polls backend for commands
