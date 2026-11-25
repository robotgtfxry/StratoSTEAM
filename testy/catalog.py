"""
Katalog sprzętu StratoSTEAM — co mamy, jak to podłączyć do Raspberry Pi 5
i jakim testem to sprawdzić.

To jest jedyne miejsce z opisami podłączeń. GUI tylko je wyświetla,
a piny bierze stąd do podświetlenia na rysunku złącza 40-pin.

Źródło danych: sprzęt, który faktycznie mamy (BME280, GY-87, INA226, kamera CSI,
RTL-SDR, ESP32-CAM, ESP32-S3, przekaźniki, GPS) + rpi-air/config.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

import hw_tests as T
from pinout import gpio_label, pin_of
from repo import air

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
GRUPA_STOL = "Moduły ESP32-S3 — test na stole"

I2C_STEPS = [
    "Wyłącz Raspberry Pi i odłącz zasilanie — czujniki podpinamy na zimno.",
    "VCC modułu → pin 1 (3.3 V). Podanie 5 V uszkodzi czujnik.",
    "GND modułu → pin 6.",
    "SDA modułu → pin 3 (GPIO2).",
    "SCL modułu → pin 5 (GPIO3).",
    "Włącz Raspberry Pi, uruchom test — najpierw „Skan magistrali I2C”.",
]

I2C_LIBS = ["python3-smbus2 (apt) lub smbus2 (pip)"]

# GY-87: jedna płytka, trzy układy (MPU-6050 + magnetometr + BMP180) na wspólnym I2C
GY87_WIRING = [
    Wire("VCC_IN", "3.3 V — pin 1", (1,), K_3V3, "płytka ma stabilizator — przyjmie też 5 V"),
    w_gnd(),
    w_gpio("SDA", 2, "magistrala wspólna dla wszystkich czujników I2C"),
    w_gpio("SCL", 3, "magistrala wspólna dla wszystkich czujników I2C"),
    Wire("3.3V (wyjście)", "niepodłączony", (), K_OTHER, "to wyjście stabilizatora płytki"),
    Wire("FSYNC / INTA / DRDY", "niepodłączone", (), K_OTHER, "nie są potrzebne"),
]
GY87_STEPS = [
    "Wyłącz Raspberry Pi i odłącz zasilanie — czujniki podpinamy na zimno.",
    "VCC_IN płytki GY-87 → pin 1 (3.3 V). Pin „3.3V” na płytce zostaw wolny.",
    "GND → pin 6.",
    "SDA → pin 3 (GPIO2), SCL → pin 5 (GPIO3) — te same co BME280.",
    "Włącz Raspberry Pi, uruchom „Skan magistrali I2C” — muszą być 0x68 i 0x77.",
]


def build_devices() -> list[Device]:
    espcam_pwr = air("ESPCAM_PWR_PIN", 17)
    espcam_baud = air("ESPCAM_STATUS_BAUD", 115200)
    alive = air("RPI_ALIVE_PIN", 26)
    shtdn = air("ESP32_SHTDN_PIN", 6)
    uart_port = air("ESP_UART_PORT", "/dev/ttyAMA0")
    uart_baud = air("ESP_UART_BAUD", 115200)

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
                "Wszystkie czujniki dzielą tę samą parę przewodów: BME280 (0x76), "
                "GY-87 = MPU-6050 (0x68) + BMP180 (0x77) + magnetometr (0x0D), INA226 (0x44).",
                "Magnetometr GY-87 pojawia się w skanie dopiero po teście MPU-6050 "
                "albo magnetometru (bypass I2C).",
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
                "Adres 0x76. Moduł ze zworką SDO na 3.3 V ma 0x77 — wtedy koliduje z BMP180 "
                "na GY-87.",
                "Temperatura mierzona jest wewnątrz obudowy modułu — na balonie "
                "będzie kilka stopni wyżej niż powietrze.",
            ],
            libs=I2C_LIBS + ["pimoroni-bme280 (pip)"],
            test=T.test_bme280,
        ),
        Device(
            id="mpu6050",
            name="GY-87: MPU-6050 — akcelerometr i żyroskop",
            group=GRUPA_BALON,
            bus=f"I2C 0x{T.MPU6050_ADDR:02X}",
            summary="Przyspieszenie i prędkość obrotu w 3 osiach — pokazuje, jak ładunek "
                    "się kołysze i kręci pod balonem. Z akcelerometru liczymy też roll / pitch.",
            wiring=GY87_WIRING,
            steps=GY87_STEPS + [
                "Połóż moduł nieruchomo na stole — test sprawdza, czy widzi 1 g w dół.",
            ],
            notes=[
                "Adres 0x68 (pin AD0 na masie), 0x69 gdy AD0 na 3.3 V.",
                "Po włączeniu MPU-6050 śpi — test go budzi i przy okazji włącza bypass I2C, "
                "żeby był widoczny magnetometr.",
                "Akcelerometr ±2 g, żyroskop ±250 °/s. Kilka °/s offsetu żyroskopu na stole "
                "to norma — kalibruje się programowo.",
                "Yaw (obrót wokół pionu) da się policzyć dopiero z magnetometrem.",
            ],
            libs=I2C_LIBS,
            test=T.test_mpu6050,
            duration="ok. 1 s",
        ),
        Device(
            id="magnetometr",
            name="GY-87: QMC5883L / HMC5883L — magnetometr (kompas)",
            group=GRUPA_BALON,
            bus=f"I2C 0x{T.QMC5883L_ADDR:02X} (QMC5883L) lub 0x{T.HMC5883L_ADDR:02X} (HMC5883L)",
            summary="Mierzy pole magnetyczne Ziemi — z niego liczymy kierunek (yaw), w którą "
                    "stronę obrócony jest ładunek.",
            wiring=GY87_WIRING,
            steps=GY87_STEPS + [
                "Odsuń moduł od magnesów, głośników i metalowych narzędzi.",
            ],
            notes=[
                "Na GY-87 magnetometr jest podpięty za MPU-6050. Widać go na magistrali "
                "dopiero po włączeniu bypassu I2C w MPU — test robi to sam.",
                "Tańsze klony GY-87 mają QMC5883L (0x0D) zamiast oryginalnego HMC5883L (0x1E) — "
                "test rozpoznaje oba.",
                "Pole Ziemi w Polsce to ok. 50 µT. Dużo więcej = magnes lub metal obok.",
                "Do prawdziwego kompasu potrzebna kalibracja (obracanie modułem w każdej osi).",
            ],
            libs=I2C_LIBS,
            test=T.test_magnetometer,
            duration="ok. 1 s",
        ),
        Device(
            id="bmp180",
            name="GY-87: BMP180 — ciśnienie i temperatura",
            group=GRUPA_BALON,
            bus=f"I2C 0x{T.BMP180_ADDR:02X}",
            summary="Drugi barometr (obok BME280) — z niego liczymy wysokość barometryczną. "
                    "Dwa czujniki ciśnienia pozwalają wychwycić, gdy jeden zacznie kłamać.",
            wiring=GY87_WIRING,
            steps=GY87_STEPS,
            notes=[
                "Adres 0x77 jest stały. BME280 musi zostać na 0x76, inaczej będzie kolizja.",
                "Zakres 300–1100 hPa, czyli do ok. 9 km. Wyżej czujnik przestaje mierzyć — "
                "w stratosferze wysokość bierzemy z GPS.",
                "Wysokość liczona wzorem ISA względem 1013.25 hPa — to nie jest wysokość GPS.",
                "Czujnik nie lubi przeciągu i światła — na balonie osłonić.",
            ],
            libs=I2C_LIBS,
            test=T.test_bmp180,
        ),
        Device(
            id="ina226",
            name="INA226 — napięcie i prąd baterii",
            group=GRUPA_BALON,
            bus=f"I2C 0x{T.INA226_ADDR:02X}, bocznik {T.INA226_SHUNT_OHMS} Ω",
            summary="Monitor zasilania: napięcie pakietu, pobór prądu, moc. "
                    "Po tym poznasz, ile jeszcze polecimy.",
            wiring=w_i2c() + [
                Wire("VIN+", "biegun + baterii", (), K_OTHER, "nie na złącze RPi"),
                Wire("VIN− / VBUS", "zasilanie odbiornika", (), K_OTHER,
                     "cały mierzony prąd płynie przez bocznik"),
            ],
            steps=I2C_STEPS + [
                "Bocznik wepnij szeregowo w linię zasilania: bateria → VIN+, VIN− → odbiornik.",
                "Masa baterii musi być wspólna z masą Raspberry Pi.",
                "VCC (3.3 V z pinu 1) zasila tylko elektronikę pomiarową modułu.",
            ],
            notes=[
                "Adres zależy od zworek A0/A1 — nasz moduł ma 0x44 (możliwe 0x40…0x4F); "
                "test sam przeszuka cały zakres, jeśli pod ustawionym adresem go nie ma.",
                f"Bocznik {T.INA226_SHUNT_OHMS} Ω (oznaczenie R100): zakres INA226 to ±81.92 mV, "
                f"czyli najwyżej ok. {81.92 / T.INA226_SHUNT_OHMS:.0f} mA. "
                "Przy większym poborze trzeba mniejszego bocznika.",
                "Napięcie mierzone do 36 V.",
                "Zero prądu przy poprawnym napięciu = bocznik wpięty równolegle zamiast szeregowo.",
                "Inną wartość bocznika lub adres ustawisz w rpi-air/config.py: "
                "INA226_SHUNT_OHMS, INA226_ADDR.",
            ],
            libs=I2C_LIBS,
            test=T.test_ina226,
        ),
    ]

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
                "Jeśli usługa rpi-air już działa, kamera jest zajęta — "
                "zatrzymaj ją: sudo systemctl stop rpi-air",
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
                "DO ZROBIENIA: tor HF nie leci w tej wersji (brak filtra) — "
                "ten test można pominąć.",
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
            name="ESP32-CAM — zasilanie",
            group=GRUPA_BALON,
            bus="USB (stałe)" if espcam_pwr is None else f"GPIO{espcam_pwr}",
            summary="Kamera jest zasilana na stałe kablem USB — nie ma czego przełączać. "
                    "Test ma sens tylko po powrocie do MOSFET-a (ESPCAM_PWR_PIN).",
            wiring=([Wire("Nakładka ESP32-CAM-MB", "dowolny port USB", (), K_OTHER)]
                    if espcam_pwr is None else
                    [w_gpio("Bramka MOSFET", espcam_pwr, "przez rezystor 100 Ω"),
                     w_5v("VCC kamery"), w_gnd("Masa systemowa (source)")]),
            steps=[
                "Podłącz kamerę kablem USB — czerwona dioda zacznie mrugać co 2 s.",
                "Czy kamera faktycznie działa, mówi test statusu ESP32-CAM.",
            ],
            notes=["Komenda espcam_pwr jest przy zasilaniu z USB ignorowana (tylko log)."],
            libs=["RPi.GPIO — na RPi 5: python3-rpi-lgpio"],
            test=T.test_espcam_power,
            duration="ok. 2 s",
        ),
        Device(
            id="espcam_status",
            name="ESP32-CAM — status po USB",
            group=GRUPA_BALON,
            bus=f"USB (CH340) @ {espcam_baud} baud",
            summary="Kamera co 5 s wypluwa linię JSON ze swoim stanem: czy nagrywa, "
                    "ile klatek, ile wolnego miejsca na karcie. Jeden kabel USB daje "
                    "zasilanie i status.",
            wiring=[Wire("Nakładka ESP32-CAM-MB", "dowolny port USB", (), K_OTHER,
                         "kabel z liniami danych")],
            steps=[
                "Włóż kartę SD (FAT32, do 32 GB) i wepnij kamerę w nakładkę ESP32-CAM-MB.",
                "Połącz nakładkę kablem USB z Raspberry Pi.",
                "Sprawdź, czy system ją widzi: lsusb | grep -i 1a86",
                "Uruchom test — nasłuchuje do 15 s, kamera raportuje co ~5 s.",
            ],
            notes=[
                "Port jest wyszukiwany automatycznie (CH340). Przy dwóch CH340 wpisz ścieżkę "
                "w rpi-air/config.py: ESPCAM_UART_PORT.",
                "Otwarcie portu może raz zrestartować kamerę — zacznie wtedy nową sesję nagrań.",
                f"Prędkość {espcam_baud} baud — tyle ustawia espcam/include/config.h "
                "(SERIAL_BAUD).",
                "Format linii: $S{\"ok\":1,\"rec\":1,\"n\":1234,\"mb\":7800} — linie bez "
                "prefiksu $S (debug, boot) są ignorowane.",
            ],
            libs=["pyserial"],
            test=T.test_espcam_status,
            duration="ok. 15 s",
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
                "Ten sam port zajmuje usługa rpi-air — zatrzymaj ją przed testem.",
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
            confirm="Test na chwilę podnosi, a potem opuszcza RPI_ALIVE.\n\n"
                    "Jeśli Raspberry Pi jest zasilane przez ESP32 (MOSFET), ESP32 uzna, że RPi "
                    "przestało działać i po ok. 60 s odetnie zasilanie — chyba że wcześniej "
                    "uruchomisz usługę rpi-air.\n\nKontynuować?",
            live=False,
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
GROUPS: list[str] = [GRUPA_BALON, GRUPA_STOL]
