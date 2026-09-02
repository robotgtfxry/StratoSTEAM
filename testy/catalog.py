"""
Katalog sprzętu StratoSTEAM — co mamy, jak to podłączyć do Raspberry Pi 5
i jakim testem to sprawdzić.

To jest jedyne miejsce z opisami podłączeń. GUI tylko je wyświetla,
a piny bierze stąd do podświetlenia na rysunku złącza 40-pin.

Źródło danych: HARDWARE.md + rpi-air/config.py + rpi-ground/config.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

import hw_tests as T
from pinout import gpio_label, pin_of
from repo import air, ground

# rodzaje linii (kolor na rysunku złącza)
K_3V3, K_5V, K_GND, K_SIG, K_OTHER = "3v3", "5v", "gnd", "gpio", "other"


@dataclass(frozen=True)
class Wire:
    """Jedno połączenie: sygnał modułu → miejsce na Raspberry Pi 5."""
    signal: str
    target: str
    pins: tuple[int, ...] = ()
    kind: str = K_SIG
    note: str = ""


@dataclass
class Device:
    id: str
    name: str
    group: str
    bus: str
    summary: str
    wiring: list[Wire]
    steps: list[str]
    notes: list[str]
    libs: list[str]
    test: Callable[[], T.Result]
    duration: str = "poniżej 1 s"
    confirm: str | None = None      # tekst ostrzeżenia dla akcji ryzykownych
    live: bool = True               # czy wolno powtarzać w trybie ciągłym

    @property
    def pins(self) -> list[int]:
        out: list[int] = []
        for w in self.wiring:
            out.extend(p for p in w.pins if p and p not in out)
        return out


# ── skróty do typowych połączeń ──────────────────────────────────────────────
def w_3v3(signal: str = "VCC") -> Wire:
    return Wire(signal, "3.3 V — pin 1", (1,), K_3V3, "albo pin 17; NIGDY 5 V")


def w_5v(signal: str = "VCC") -> Wire:
    return Wire(signal, "5 V — pin 2", (2,), K_5V, "albo pin 4")


def w_gnd(signal: str = "GND") -> Wire:
    return Wire(signal, "GND — pin 6", (6,), K_GND,
                "dowolny GND: 6, 9, 14, 20, 25, 30, 34, 39")


def w_gpio(signal: str, bcm: int, note: str = "") -> Wire:
    return Wire(signal, gpio_label(bcm), (pin_of(bcm) or 0,), K_SIG, note)


def w_i2c() -> list[Wire]:
    return [w_3v3(), w_gnd(),
            w_gpio("SDA", 2, "magistrala wspólna dla wszystkich czujników I2C"),
            w_gpio("SCL", 3, "magistrala wspólna dla wszystkich czujników I2C")]


GRUPA_BALON = "Raspberry Pi 5 — balon"
GRUPA_ZIEMIA = "Raspberry Pi 5 — stacja naziemna"
GRUPA_STOL = "Moduły ESP32 — test na stole"

I2C_STEPS = [
    "Wyłącz Raspberry Pi i odłącz zasilanie — czujniki podpinamy na zimno.",
    "VCC modułu → pin 1 (3.3 V). Podanie 5 V uszkodzi czujnik.",
    "GND modułu → pin 6.",
    "SDA modułu → pin 3 (GPIO2).",
    "SCL modułu → pin 5 (GPIO3).",
    "Włącz Raspberry Pi, uruchom test — najpierw „Skan magistrali I2C”.",
]

I2C_LIBS = ["python3-smbus2 (apt) lub smbus2 (pip)"]


def build_devices() -> list[Device]:
    hx = air("HX711_SENSORS", T._HX711_DEFAULT)
    espcam_pwr = air("ESPCAM_PWR_PIN", 17)
    espcam_st = air("ESPCAM_STATUS_PIN", 4)
    espcam_baud = air("ESPCAM_STATUS_BAUD", 115200)
    alive = air("RPI_ALIVE_PIN", 26)
    shtdn = air("ESP32_SHTDN_PIN", 6)
    uart_port = air("ESP_UART_PORT", "/dev/ttyAMA0")
    uart_baud = air("ESP_UART_BAUD", 115200)
    lora_dio0 = ground("LORA_DIO0_PIN", 25)
    lora_freq = ground("LORA_FREQ", 433.0)
    hf_freq = ground("HF_DEFAULT_FREQ_HZ", 7_100_000)
    hf_ptt = ground("HF_PTT_PIN", 24)

    devices: list[Device] = [
        Device(
            id="i2c",
            name="Magistrala I2C — skan",
            group=GRUPA_BALON,
            bus="I2C-1 (GPIO2 / GPIO3)",
            summary="Zaczynaj od tego testu. Pokazuje wszystkie układy widoczne na "
                    "magistrali — jak i2cdetect. Jeśli czujnika tu nie ma, to jest "
                    "problem z kablami albo zasilaniem, a nie z biblioteką.",
            wiring=w_i2c(),
            steps=I2C_STEPS,
            notes=[
                "Cztery czujniki dzielą tę samą parę przewodów: BME280 (0x76), "
                "MS5611 (0x77), BNO085 (0x4A), INA219 (0x40).",
                "Dwa moduły pod tym samym adresem = żaden nie zadziała.",
                "Rezystory podciągające są już na modułach.",
            ],
            libs=I2C_LIBS,
            test=T.test_i2c_scan,
            duration="ok. 2 s",
        ),
        Device(
            id="bme280",
            name="BME280 — temperatura, wilgotność, ciśnienie",
            group=GRUPA_BALON,
            bus=f"I2C 0x{air('BME280_ADDR', 0x76):02X}",
            summary="Podstawowy czujnik atmosferyczny ładunku. W telemetrii pola "
                    "temp / hum / pres.",
            wiring=w_i2c(),
            steps=I2C_STEPS,
            notes=[
                "Adres 0x76. Moduł ze zworką SDO na 3.3 V ma 0x77 — wtedy koliduje z MS5611.",
                "Temperatura mierzona jest wewnątrz obudowy modułu — na balonie "
                "będzie kilka stopni wyżej niż powietrze.",
            ],
            libs=I2C_LIBS + ["bme280 (pip)"],
            test=T.test_bme280,
        ),
        Device(
            id="ms5611",
            name="MS5611 — ciśnienie precyzyjne / wysokość",
            group=GRUPA_BALON,
            bus=f"I2C 0x{air('MS5611_ADDR', 0x77):02X}",
            summary="Barometr o dużej rozdzielczości — z niego liczymy wysokość lotu "
                    "(pola p2 / alt2).",
            wiring=w_i2c(),
            steps=I2C_STEPS,
            notes=[
                "Adres 0x77 (pin CSB niepodłączony). CSB na masę → 0x76, czyli kolizja z BME280.",
                "Wysokość liczona wzorem ISA względem 1013.25 hPa — to nie jest wysokość GPS.",
                "Czujnik nie lubi przeciągu i światła — na balonie osłonić.",
            ],
            libs=I2C_LIBS,
            test=T.test_ms5611,
        ),
        Device(
            id="bno085",
            name="BNO085 — IMU 9-DOF (orientacja)",
            group=GRUPA_BALON,
            bus=f"I2C 0x{air('BNO085_ADDR', 0x4A):02X}",
            summary="Roll / pitch / yaw i akcelerometr — pokazuje jak ładunek się kołysze "
                    "i kręci pod balonem.",
            wiring=w_i2c(),
            steps=I2C_STEPS + [
                "Połóż moduł nieruchomo na stole — test sprawdza, czy widzi 1 g w dół.",
            ],
            notes=[
                "Adres 0x4A (0x4B przy podciągniętym pinie ADR).",
                "Układ rozciąga zegar I2C. Przy błędach dopisz w /boot/firmware/config.txt: "
                "dtparam=i2c_arm_baudrate=50000",
                "Po włączeniu potrzebuje 2-3 s zanim fuzja czujników poda orientację.",
            ],
            libs=["adafruit-circuitpython-bno08x", "adafruit-blinka"],
            test=T.test_bno085,
            duration="ok. 1 s",
        ),
        Device(
            id="ina219",
            name="INA219 — napięcie i prąd baterii",
            group=GRUPA_BALON,
            bus=f"I2C 0x{air('INA219_ADDR', 0x40):02X}, bocznik "
                f"{air('INA219_SHUNT_OHMS', 0.1)} Ω",
            summary="Monitor zasilania: napięcie pakietu, pobór prądu, moc "
                    "(pola vbat / imA). Po tym poznasz, ile jeszcze polecimy.",
            wiring=w_i2c() + [
                Wire("Vin+", "biegun + baterii", (), K_OTHER, "nie na złącze RPi"),
                Wire("Vin−", "zasilanie odbiornika", (), K_OTHER,
                     "cały mierzony prąd płynie przez te dwa zaciski"),
            ],
            steps=I2C_STEPS + [
                "Bocznik wepnij szeregowo w linię zasilania: bateria → Vin+, Vin− → odbiornik.",
                "VCC (3.3 V z pinu 1) zasila tylko elektronikę pomiarową modułu.",
            ],
            notes=[
                "Adres zależy od zworek A0/A1 — domyślnie 0x40.",
                "Bocznik 0.1 Ω: maksymalny mierzalny prąd ok. 3.2 A.",
                "Zero prądu przy poprawnym napięciu = bocznik wpięty równolegle zamiast szeregowo.",
            ],
            libs=I2C_LIBS + ["pi-ina219 (pip)"],
            test=T.test_ina219,
        ),
    ]

    for i in range(4):
        pins = hx[i] if i < len(hx) else T._HX711_DEFAULT[i]
        dt, sck = pins["dt"], pins["sck"]
        devices.append(Device(
            id=f"hx711_{i}",
            name=f"HX711 #{i} — tensometr ({T.HX711_LABELS[i]})",
            group=GRUPA_BALON,
            bus=f"GPIO bit-bang, DT GPIO{dt} / SCK GPIO{sck}",
            summary="24-bitowy przetwornik siły w narożniku ramy zawieszenia. Cztery sztuki "
                    "razem mówią, jak rozkłada się masa ładunku (pola sg0…sg3).",
            wiring=[w_3v3(), w_gnd(),
                    w_gpio("DT (data)", dt, "wyjście danych z HX711"),
                    w_gpio("SCK (clock)", sck, "zegar z Raspberry Pi"),
                    Wire("E+ / E−", "mostek tensometryczny — zasilanie", (), K_OTHER,
                         "czerwony / czarny przewód belki"),
                    Wire("A+ / A−", "mostek tensometryczny — sygnał", (), K_OTHER,
                         "zielony / biały przewód belki")],
            steps=[
                "Wyłącz Raspberry Pi.",
                "VCC modułu → pin 1 (3.3 V), GND → pin 6.",
                f"DT → {gpio_label(dt)}.",
                f"SCK → {gpio_label(sck)}.",
                "Tensometr do zacisków: E+ E− (zasilanie mostka), A+ A− (sygnał).",
                "Bez podpiętego mostka HX711 nie zgłosi gotowości — test to wykryje.",
                "Włącz RPi i uruchom test. Naciśnij belkę palcem — wskazanie musi drgnąć.",
            ],
            notes=[
                "Moduł tarowany jest przy starcie — waga startuje od zera.",
                f"reference_unit = {air('HX711_REFERENCE_UNIT', 1.0)} — do prawdziwych gramów "
                "trzeba kalibracji odważnikiem (osobno dla każdego kanału).",
                "Zamienione A+ / A− dają wskazania ujemne — to nie awaria.",
                "Każdy kanał ma własne piny — cztery HX711 nie mogą dzielić DT/SCK.",
            ],
            libs=["RPi.GPIO — na RPi 5: python3-rpi-lgpio"],
            test=partial(T.test_hx711, i),
            duration="ok. 2 s",
        ))

    devices += [
        Device(
            id="camera",
            name="Kamera CSI — Raspberry Pi Camera",
            group=GRUPA_BALON,
            bus="złącze CAM0 (15-pin FFC)",
            summary="Nagrywa H.264 na dysk przez cały lot i na żądanie robi małe zdjęcie "
                    "160×120, które leci przez LoRa.",
            wiring=[Wire("Taśma FFC", "złącze CAM0", (), K_OTHER,
                         "CAM0 to złącze bliżej gniazda zasilania"),
                    Wire("Styki taśmy", "w stronę radiatora / złącz HDMI", (), K_OTHER)],
            steps=[
                "Wyłącz Raspberry Pi.",
                "Podnieś czarny zaczep złącza CAM0, wsuń taśmę, dociśnij zaczep.",
                "Raspberry Pi 5 ma węższą taśmę (22-pin) po stronie płytki — użyj taśmy z zestawu.",
                "Włącz RPi i sprawdź: rpicam-hello --list-cameras",
                "Uruchom test — zrobi zdjęcie 640×480 i sprawdzi, czy nie jest czarne.",
            ],
            notes=[
                f"Nagrania trafiają do {air('CAM_RECORD_DIR', '/home/pi/stratosteam-video')}.",
                "Jeśli usługa stratosteam-air już działa, kamera jest zajęta — "
                "zatrzymaj ją: sudo systemctl stop stratosteam-air",
                "Zdejmij folię z obiektywu przed lotem.",
            ],
            libs=["python3-picamera2 (apt)"],
            test=T.test_camera,
            duration="ok. 3 s",
        ),
        Device(
            id="rtlsdr",
            name="RTL-SDR — odbiornik HF",
            group=GRUPA_BALON,
            bus="USB",
            summary=f"Mierzy siłę sygnału nadajnika naziemnego na "
                    f"{air('SDR_TARGET_FREQ', 7100000) / 1e6:.3f} MHz. Wynik w dBFS leci "
                    f"w telemetrii jako hfdb.",
            wiring=[Wire("Dongle", "dowolny port USB", (), K_OTHER),
                    Wire("Antena HF", "gniazdo SMA dongla", (), K_OTHER,
                         "bez anteny zobaczysz tylko szum")],
            steps=[
                "Wepnij dongle w port USB Raspberry Pi.",
                "Przykręć antenę HF do gniazda SMA.",
                "Sprawdź, czy system go widzi: lsusb | grep -i rtl",
                "Uruchom test — zmierzy moc w okolicy nośnej.",
            ],
            notes=[
                "Strojenie jest 100 kHz poniżej celu — to omija szpilkę DC przetwornika.",
                "Poziom ok. −80 dBFS to szum własny: nadajnik naziemny jest wyłączony "
                "albo nie ma anteny.",
                "Jeśli dongle nie startuje, zablokuj sterownik DVB "
                "(blacklist dvb_usb_rtl28xxu) i zrestartuj.",
            ],
            libs=["pyrtlsdr", "numpy", "rtl-sdr (apt)"],
            test=T.test_rtlsdr,
            duration="ok. 2 s",
        ),
        Device(
            id="espcam_pwr",
            name="ESP32-CAM — zasilanie przez MOSFET",
            group=GRUPA_BALON,
            bus=f"GPIO{espcam_pwr}",
            summary="Kamera wisi na tranzystorze po stronie masy. Stan wysoki na GPIO = "
                    "MOSFET otwarty = kamera zasilona. Dzięki temu można ją wyłączyć "
                    "w locie i oszczędzić prąd.",
            wiring=[w_gpio("Bramka MOSFET", espcam_pwr, "przez rezystor 100 Ω"),
                    w_5v("VCC kamery"), w_gnd("Masa systemowa (source)")],
            steps=[
                "Bramka BSS138 przez 100 Ω do GPIO, plus 10 kΩ z bramki do masy.",
                "Source tranzystora → masa systemu, Drain → GND kamery.",
                "VCC kamery → 5 V (pin 2 lub 4).",
                "Uruchom test — włączy kanał na ~0.8 s i wyłączy.",
                "Patrz na diodę kamery: powinna mrugnąć.",
            ],
            notes=[
                "Podciągnięcie 10 kΩ do masy trzyma kamerę wyłączoną w czasie startu RPi.",
                "Test sprawdza tylko stan pinu — czy kamera faktycznie wstała, "
                "mówi test statusu ESP32-CAM.",
                "Komenda w locie: {\"cmd\":\"espcam_pwr\",\"on\":true}",
            ],
            libs=["RPi.GPIO — na RPi 5: python3-rpi-lgpio"],
            test=T.test_espcam_power,
            duration="ok. 2 s",
        ),
        Device(
            id="espcam_status",
            name="ESP32-CAM — status po UART",
            group=GRUPA_BALON,
            bus=f"bit-bang serial {espcam_baud} baud",
            summary="Kamera co 5 s wypluwa linię JSON ze swoim stanem: czy nagrywa, "
                    "ile klatek, ile wolnego miejsca na karcie.",
            wiring=[w_gpio("TX kamery (GPIO1 / U0TX)", espcam_st, "wejście, poziom 3.3 V"),
                    w_gnd("Masa wspólna z kamerą")],
            steps=[
                "Najpierw włącz zasilanie kamery (poprzedni test).",
                f"GPIO1 (U0TX) kamery → {gpio_label(espcam_st)}.",
                "Masa kamery musi być wspólna z masą Raspberry Pi.",
                "Uruchom test — nasłuchuje 8 s, kamera raportuje co ~5 s.",
            ],
            notes=[
                f"Prędkość {espcam_baud} baud — tyle ustawia espcam/include/config.h "
                "(SERIAL_BAUD).",
                "Format linii: $S{\"ok\":1,\"rec\":1,\"n\":1234,\"mb\":7800} — linie bez "
                "prefiksu $S (debug, boot) są ignorowane.",
                "Odczyt idzie przez pigpio, a pigpio nie wspiera Raspberry Pi 5 — "
                "na RPi 5 ten kanał trzeba przepisać na lgpio albo sprzętowy UART.",
                "Poziomy napięć są zgodne (3.3 V ↔ 3.3 V), konwerter nie jest potrzebny.",
            ],
            libs=["pigpio + demon pigpiod"],
            test=T.test_espcam_status,
            duration="ok. 8 s",
            live=False,
        ),
        Device(
            id="esp_uart",
            name="UART Raspberry Pi 5 ↔ ESP32-S3",
            group=GRUPA_BALON,
            bus=f"{uart_port} @ {uart_baud} baud, 8N1",
            summary="Kanał, którym RPi wysyła dane czujników do ESP32 (a ten dalej przez LoRa) "
                    "i którym wracają komendy.",
            wiring=[w_gpio("TXD → RX ESP32 (GPIO3)", 14, "dane czujników w stronę ESP32"),
                    w_gpio("RXD ← TX ESP32 (GPIO14)", 15, "komendy z ESP32"),
                    w_gnd("Masa wspólna z ESP32")],
            steps=[
                "Połącz na krzyż: pin 8 (TXD) → RX ESP32, pin 10 (RXD) ← TX ESP32.",
                "Masa wspólna — bez tego UART nie zadziała.",
                "W raspi-config: konsola na porcie szeregowym WYŁĄCZONA, sam port WŁĄCZONY.",
                "Uruchom test — wyśle ping i posłucha przez 6 s.",
                "Test samego kabla: zewrzyj pin 8 z pinem 10 — ping wróci jako echo.",
            ],
            notes=[
                "Cisza nie musi znaczyć awarii: ESP32 wysyła coś tylko wtedy, gdy ma komendę.",
                "Ten sam port zajmuje usługa stratosteam-air — zatrzymaj ją przed testem.",
                "Dane w stronę ESP32: temp, hum, pres, p2, alt2, roll, pit, yaw, ax, ay, az, "
                "vbat, imA, dsku, dskf, hfdb, sg0-sg3.",
            ],
            libs=["pyserial"],
            test=T.test_esp_uart,
            duration="ok. 6 s",
            live=False,
        ),
        Device(
            id="power_signals",
            name="Sygnały GPIO Raspberry Pi 5 ↔ ESP32-S3",
            group=GRUPA_BALON,
            bus=f"GPIO{alive} (wyjście) / GPIO{shtdn} (wejście)",
            summary="Dwie linie życia: RPi mówi „żyję”, ESP32 prosi o wyłączenie systemu "
                    "przed odcięciem zasilania.",
            wiring=[w_gpio("RPI_ALIVE → ESP32 GPIO6", alive, "wyjście z RPi"),
                    w_gpio("ESP32_SHTDN ← ESP32 GPIO7", shtdn, "wejście, podciągnięte do masy"),
                    w_gnd("Masa wspólna")],
            steps=[
                f"{gpio_label(alive)} → GPIO6 ESP32.",
                f"{gpio_label(shtdn)} ← GPIO7 ESP32.",
                "Masa wspólna.",
                "Uruchom test — przełączy RPI_ALIVE i odczyta linię shutdown.",
            ],
            notes=[
                "Stan wysoki na linii shutdown w locie = ESP32 chce, żeby RPi się wyłączyła.",
                "Test zostawia RPI_ALIVE w stanie niskim — po teście uruchom usługę lotu.",
            ],
            libs=["RPi.GPIO — na RPi 5: python3-rpi-lgpio"],
            test=T.test_power_signals,
            duration="ok. 1 s",
        ),
        Device(
            id="relays",
            name="2× przekaźnik HJR1-2C — zwalnianie linek",
            group=GRUPA_BALON,
            bus=f"GPIO{T.RELAY_PINS[0]} / GPIO{T.RELAY_PINS[1]}",
            summary="Mechanizm odczepienia ładunku od balonu. Test daje krótki impuls — "
                    "przekaźnik ma kliknąć.",
            wiring=[w_gpio("Baza tranzystora #0", T.RELAY_PINS[0], "przez rezystor 100 Ω"),
                    w_gpio("Baza tranzystora #1", T.RELAY_PINS[1], "przez rezystor 100 Ω"),
                    w_3v3("Cewka (+)"), w_gnd("Emiter tranzystorów")],
            steps=[
                "ZDEJMIJ LINKI z mechanizmu przed testem.",
                "Cewka 3 V pobiera ~70 mA — nigdy prosto z GPIO (limit 16 mA).",
                "GPIO → 100 Ω → baza 2N2222/BC547, emiter → masa, kolektor → cewka (−).",
                "Cewka (+) → 3.3 V, dioda 1N4007 równolegle do cewki (katoda do 3.3 V).",
                "Uruchom test — impuls 300 ms na każdy kanał.",
            ],
            notes=[
                "Bez diody 1N4007 impuls samoindukcji cewki uszkodzi tranzystor.",
                "Komenda w locie: {\"cmd\":\"release_line\",\"line\":0|1|-1}",
                "Po teście GPIO wraca do stanu niskiego — cewka nie jest trzymana pod napięciem.",
            ],
            libs=["RPi.GPIO — na RPi 5: python3-rpi-lgpio"],
            test=partial(T.test_relays, -1),
            duration="ok. 2 s",
            confirm="Test poda napięcie na oba przekaźniki zwalniania linek.\n\n"
                    "Jeśli linki są zapięte w mechanizmie, ładunek zostanie zwolniony!\n\n"
                    "Czy mechanizm jest rozpięty i można kontynuować?",
            live=False,
        ),
        Device(
            id="lora",
            name="LoRa SX1278 — obecność modułu",
            group=GRUPA_ZIEMIA,
            bus=f"SPI{ground('LORA_SPI_BUS', 0)}.{ground('LORA_SPI_CS', 0)}, {lora_freq} MHz",
            summary="Sprawdza, czy stacja naziemna widzi radio: rejestr wersji SX1278 "
                    "musi zwrócić 0x12.",
            wiring=[w_3v3(), w_gnd(),
                    w_gpio("SCK", 11, "SPI0 SCLK"),
                    w_gpio("MOSI", 10, "SPI0 MOSI"),
                    w_gpio("MISO", 9, "SPI0 MISO"),
                    w_gpio("NSS / CS", 8, "SPI0 CE0"),
                    w_gpio("DIO0", lora_dio0, "zgłoszenie odebrania pakietu"),
                    Wire("RST", "niepodłączony", (), K_OTHER,
                         "moduł ma własne podciągnięcie; opcjonalnie na wolny GPIO"),
                    Wire("ANT", "antena 433 MHz", (), K_OTHER,
                         "nigdy nie nadawaj bez anteny")],
            steps=[
                "Wyłącz Raspberry Pi.",
                "VCC → pin 1 (3.3 V) — 5 V zniszczy moduł. GND → pin 6.",
                "SCK → pin 23, MOSI → pin 19, MISO → pin 21, NSS → pin 24.",
                f"DIO0 → {gpio_label(lora_dio0)}.",
                "Przykręć antenę 433 MHz.",
                "Włącz SPI w raspi-config, zrestartuj i uruchom test.",
            ],
            notes=[
                "Odpowiedź 0x00 albo 0xFF to najczęściej zamienione MISO z MOSI.",
                "Na balonie LoRa wisi na ESP32 — po stronie Raspberry Pi jest tylko "
                "na stacji naziemnej.",
                f"Ustawienia z rpi-ground/config.py: {lora_freq} MHz, SF{ground('LORA_SF', 10)}, "
                f"BW {ground('LORA_BW', 125000) // 1000} kHz, CR 4:{ground('LORA_CR', 5)}.",
            ],
            libs=["spidev"],
            test=T.test_lora_present,
        ),
        Device(
            id="lora_rx",
            name="LoRa SX1278 — nasłuch pakietu z balonu",
            group=GRUPA_ZIEMIA,
            bus=f"{lora_freq} MHz, SF{ground('LORA_SF', 10)}",
            summary="Prawdziwy test łącza: 12 s nasłuchu. Jeśli ESP32 nadaje, zobaczysz "
                    "RSSI, SNR i początek pakietu.",
            wiring=[w_3v3(), w_gnd(),
                    w_gpio("SCK", 11), w_gpio("MOSI", 10), w_gpio("MISO", 9),
                    w_gpio("NSS / CS", 8), w_gpio("DIO0", lora_dio0),
                    Wire("ANT", "antena 433 MHz", (), K_OTHER)],
            steps=[
                "Podłączenie identyczne jak w teście obecności modułu.",
                "Włącz ESP32 na balonie — nadaje pakiet co ok. 5 s.",
                "Uruchom test i poczekaj 12 s.",
            ],
            notes=[
                "Obie strony muszą mieć te same: częstotliwość, SF, BW, CR i sync word 0x12.",
                "RSSI powyżej −100 dBm na stole to dobry wynik; przy słabym sygnale "
                "spada w stronę −120 dBm.",
                "Błąd CRC = sygnał na granicy czułości albo niedopasowane ustawienia.",
            ],
            libs=["spidev"],
            test=T.test_lora_rx,
            duration="ok. 12 s",
            live=False,
        ),
        Device(
            id="hf_tx",
            name="AD9833 + RD06HHF1 — nadajnik HF",
            group=GRUPA_ZIEMIA,
            bus=f"SPI{ground('AD9833_SPI_BUS', 1)}.{ground('AD9833_SPI_CS', 1)}, "
                f"{hf_freq / 1e6:.3f} MHz",
            summary="Generator sygnału do eksperymentu jonosferycznego. Test tylko ustawia "
                    "częstotliwość — NIE kluczuje PTT, więc nic nie idzie w eter.",
            wiring=[w_3v3(), w_gnd(),
                    w_gpio("SCLK", 21, "SPI1 SCLK"),
                    w_gpio("MOSI / SDATA", 20, "SPI1 MOSI"),
                    w_gpio("FSYNC / CS", 17, "SPI1 CE1"),
                    w_gpio("PTT (kluczowanie PA)", hf_ptt, "stan wysoki = wzmacniacz nadaje"),
                    Wire("OUT", "filtr LPF → RD06HHF1", (), K_OTHER),
                    Wire("ANT", "antena 40 m albo sztuczne obciążenie", (), K_OTHER)],
            steps=[
                "Włącz SPI1: dopisz dtoverlay=spi1-3cs w /boot/firmware/config.txt i zrestartuj.",
                "SCLK → pin 40, MOSI → pin 38, FSYNC → pin 11.",
                f"PTT → {gpio_label(hf_ptt)}.",
                "Wyjście AD9833 → filtr dolnoprzepustowy → wzmacniacz RD06HHF1.",
                "Podłącz antenę albo sztuczne obciążenie ZANIM zaczniesz nadawać.",
                "Uruchom test — zapisze rejestry generatora, PTT zostanie w stanie niskim.",
            ],
            notes=[
                "AD9833 nie ma odczytu rejestrów — sam sygnał sprawdzisz oscyloskopem na OUT.",
                "Nadawanie w paśmie 40 m wymaga uprawnień krótkofalarskich.",
                "Praca wzmacniacza bez obciążenia niszczy stopień mocy.",
            ],
            libs=["spidev"],
            test=T.test_hf_tx,
            confirm="Test zapisze rejestry generatora AD9833.\n\n"
                    "PTT nie będzie kluczowane (brak emisji), ale sprawdź, czy do wyjścia "
                    "podłączona jest antena albo sztuczne obciążenie.\n\nKontynuować?",
            live=False,
        ),
        Device(
            id="gps",
            name="GPS NEO-M8N — pozycja, wysokość, prędkość",
            group=GRUPA_STOL,
            bus="UART 9600 baud (NMEA)",
            summary="W locie GPS wisi na ESP32. Ten test służy do sprawdzenia modułu na stole: "
                    "podpinasz go do Raspberry Pi i patrzysz, czy nadaje NMEA i łapie fix.",
            wiring=[w_3v3(), w_gnd(),
                    w_gpio("TX modułu → RXD RPi", 15, "dane NMEA płyną tylko w tę stronę"),
                    Wire("RX modułu", "niepodłączony", (), K_OTHER,
                         "w locie ESP32 też nic nie wysyła do GPS"),
                    Wire("Antena", "ceramiczna / zewnętrzna", (), K_OTHER,
                         "wystaw za okno albo na zewnątrz")],
            steps=[
                "Wyłącz Raspberry Pi.",
                "VCC → pin 1 (3.3 V), GND → pin 6.",
                "TX modułu → pin 10 (GPIO15, RXD). Wyjście RX modułu zostaw wolne.",
                "Alternatywa: przejściówka USB-TTL — test sam znajdzie /dev/ttyUSB0.",
                "Wystaw antenę pod otwarte niebo i uruchom test (nasłuch 5 s).",
                "Zimny start to nawet 60-90 s do pierwszego fixa.",
            ],
            notes=[
                "W locie: TX GPS → GPIO4 ESP32, a pozycja dołączana jest do każdego pakietu LoRa.",
                "Migająca dioda na module = fix złapany.",
                "Prędkość domyślna 9600 baud.",
                "W budynku modułu nie przetestujesz do końca — NMEA będzie, fixa nie.",
            ],
            libs=["pyserial", "pynmea2"],
            test=T.test_gps,
            duration="ok. 5 s",
            live=False,
        ),
    ]
    return devices


DEVICES: list[Device] = build_devices()
BY_ID: dict[str, Device] = {d.id: d for d in DEVICES}
GROUPS: list[str] = [GRUPA_BALON, GRUPA_ZIEMIA, GRUPA_STOL]
