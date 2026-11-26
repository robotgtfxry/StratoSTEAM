# StratoSTEAM — Ground station configuration
import os

# LoRa RX (must match air config exactly)
LORA_FREQ = 433.0
LORA_SF = 10
LORA_BW = 125000
LORA_CR = 5
# dBm — moc uplink do balonu. 20 = maksimum SX1278 (PA_BOOST + PA_DAC); stacja nadaje
# rzadko (tylko komendy), więc mieści się w limicie 1% czasu dla 20 dBm.
LORA_TX_POWER = 20
LORA_SPI_BUS = 0
LORA_SPI_CS = 0
LORA_DIO0_PIN = 25

# Znak wywoławczy stacji naziemnej — dołączany do każdej komendy nadawanej do sondy
# (pole "z"). Znak sondy ustawia się w aplikacji (Ustawienia), domyślnie SP8DEV-1.
STATION_CALLSIGN = os.environ.get("STRATO_CALLSIGN", "SP8DEV")

# Backend server
# Klucz API nie może być w repo: na stacji jest w /etc/stratosteam.env (czyta go usługa).
BACKEND_URL = os.environ.get("STRATO_BACKEND_URL", "http://localhost:8000")
BACKEND_API_KEY = os.environ.get("STRATO_API_KEY", "change-me-in-production")

# Podgląd kamery balonu po sieci (działa na ziemi, gdy balon jest w Tailscale)
PREVIEW_URL = os.environ.get("STRATO_PREVIEW_URL", "http://100.89.237.68:8081/foto.jpg")

# How often to flush buffered packets when offline (seconds)
OFFLINE_FLUSH_INTERVAL_S = 10

# AD9833 + LPF-B0R35+ + RD06HHF1 — HF ionospheric test transmitter
# TODO(HF): DO ZROBIENIA — wyłączone, brakuje jednego filtra w torze HF.
#           Lista rzeczy do zrobienia przed włączeniem: HARDWARE.md → „Tor HF”.
#           Włączać razem z SDR_ENABLED w rpi-air/config.py i w Flutterze (hf_service.dart).
HF_ENABLED     = False
AD9833_SPI_BUS = 1
AD9833_SPI_CS  = 1
AD9833_MCLK_HZ = 25_000_000     # 25 MHz crystal on AD9833 module
HF_PTT_PIN     = 24             # BCM GPIO — keys the RD06HHF1 via PTT line
HF_DEFAULT_FREQ_HZ = 7_100_000  # 7.1 MHz (40m band) as default test frequency
HF_POLL_INTERVAL_S = 1.0        # how often rpi-ground polls backend for commands
