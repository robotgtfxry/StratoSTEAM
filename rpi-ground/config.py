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
