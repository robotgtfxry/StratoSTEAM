"""
Mapa 40-pinowego złącza GPIO Raspberry Pi 5 (układ identyczny jak RPi 3/4/Zero).

Używana przez GUI do rysowania złącza i podświetlania pinów wybranego czujnika,
oraz przez katalog urządzeń do opisu "GPIO17 (pin 11)".
"""

KIND_3V3 = "3v3"
KIND_5V = "5v"
KIND_GND = "gnd"
KIND_GPIO = "gpio"

# (pin fizyczny, etykieta, numer BCM lub None, rodzaj, funkcja alternatywna)
HEADER: list[tuple[int, str, int | None, str, str]] = [
    (1,  "3.3V",   None, KIND_3V3,  "zasilanie 3.3 V"),
    (2,  "5V",     None, KIND_5V,   "zasilanie 5 V"),
    (3,  "GPIO2",  2,    KIND_GPIO, "I2C1 SDA"),
    (4,  "5V",     None, KIND_5V,   "zasilanie 5 V"),
    (5,  "GPIO3",  3,    KIND_GPIO, "I2C1 SCL"),
    (6,  "GND",    None, KIND_GND,  "masa"),
    (7,  "GPIO4",  4,    KIND_GPIO, "GPCLK0"),
    (8,  "GPIO14", 14,   KIND_GPIO, "UART TXD"),
    (9,  "GND",    None, KIND_GND,  "masa"),
    (10, "GPIO15", 15,   KIND_GPIO, "UART RXD"),
    (11, "GPIO17", 17,   KIND_GPIO, "SPI1 CE1"),
    (12, "GPIO18", 18,   KIND_GPIO, "SPI1 CE0 / PCM CLK"),
    (13, "GPIO27", 27,   KIND_GPIO, ""),
    (14, "GND",    None, KIND_GND,  "masa"),
    (15, "GPIO22", 22,   KIND_GPIO, ""),
    (16, "GPIO23", 23,   KIND_GPIO, ""),
    (17, "3.3V",   None, KIND_3V3,  "zasilanie 3.3 V"),
    (18, "GPIO24", 24,   KIND_GPIO, ""),
    (19, "GPIO10", 10,   KIND_GPIO, "SPI0 MOSI"),
    (20, "GND",    None, KIND_GND,  "masa"),
    (21, "GPIO9",  9,    KIND_GPIO, "SPI0 MISO"),
    (22, "GPIO25", 25,   KIND_GPIO, ""),
    (23, "GPIO11", 11,   KIND_GPIO, "SPI0 SCLK"),
    (24, "GPIO8",  8,    KIND_GPIO, "SPI0 CE0"),
    (25, "GND",    None, KIND_GND,  "masa"),
    (26, "GPIO7",  7,    KIND_GPIO, "SPI0 CE1"),
    (27, "ID_SD",  0,    KIND_GPIO, "EEPROM HAT — nie używać"),
    (28, "ID_SC",  1,    KIND_GPIO, "EEPROM HAT — nie używać"),
    (29, "GPIO5",  5,    KIND_GPIO, ""),
    (30, "GND",    None, KIND_GND,  "masa"),
    (31, "GPIO6",  6,    KIND_GPIO, ""),
    (32, "GPIO12", 12,   KIND_GPIO, "PWM0"),
    (33, "GPIO13", 13,   KIND_GPIO, "PWM1"),
    (34, "GND",    None, KIND_GND,  "masa"),
    (35, "GPIO19", 19,   KIND_GPIO, "SPI1 MISO"),
    (36, "GPIO16", 16,   KIND_GPIO, "SPI1 CE2"),
    (37, "GPIO26", 26,   KIND_GPIO, ""),
    (38, "GPIO20", 20,   KIND_GPIO, "SPI1 MOSI"),
    (39, "GND",    None, KIND_GND,  "masa"),
    (40, "GPIO21", 21,   KIND_GPIO, "SPI1 SCLK"),
]

BY_PIN: dict[int, tuple[int, str, int | None, str, str]] = {row[0]: row for row in HEADER}
BCM_TO_PIN: dict[int, int] = {row[2]: row[0] for row in HEADER if row[2] is not None}


def pin_of(bcm: int) -> int | None:
    """Numer pinu fizycznego dla numeru BCM."""
    return BCM_TO_PIN.get(bcm)


def gpio_label(bcm: int) -> str:
    """'GPIO17 (pin 11)' — gotowy opis do tabeli podłączenia."""
    pin = pin_of(bcm)
    return f"GPIO{bcm} (pin {pin})" if pin else f"GPIO{bcm}"


def pin_label(pin: int) -> str:
    """'pin 3 — GPIO2 (I2C1 SDA)'"""
    row = BY_PIN.get(pin)
    if not row:
        return f"pin {pin}"
    _, name, bcm, _kind, alt = row
    txt = f"pin {pin} — {name}"
    return f"{txt} ({alt})" if alt else txt


# Piny 3.3V / 5V / GND — przydatne przy opisie zasilania modułu
PINS_3V3 = [row[0] for row in HEADER if row[3] == KIND_3V3]
PINS_5V = [row[0] for row in HEADER if row[3] == KIND_5V]
PINS_GND = [row[0] for row in HEADER if row[3] == KIND_GND]
