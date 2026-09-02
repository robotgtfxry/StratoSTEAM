"""
Testy sprzętowe StratoSTEAM — warstwa "co i jak zmierzyć".

Zasady:
  * żaden test nie rzuca wyjątkiem — błąd wraca jako Result(FAIL, ...),
  * każdy błąd ma podpowiedzi (co sprawdzić, co doinstalować),
  * tryb symulacji (set_simulation(True)) pozwala uruchomić GUI na zwykłym PC.
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import time
from dataclasses import dataclass, field

from repo import air, ground, is_pi5, load_repo_module

# ── statusy wyników ──────────────────────────────────────────────────────────
OK = "OK"            # czujnik odpowiada, wartości sensowne
WARN = "WARN"        # odpowiada, ale coś jest podejrzane
FAIL = "FAIL"        # nie odpowiada / błąd komunikacji
MISSING = "MISSING"  # brak biblioteki lub interfejsu w systemie
INFO = "INFO"        # test wykonany, wynik wymaga oceny człowieka
PENDING = "PENDING"  # jeszcze nie testowano (używane przez GUI)


@dataclass
class Result:
    status: str
    message: str
    values: dict[str, str] = field(default_factory=dict)
    hints: list[str] = field(default_factory=list)


SIMULATE = False


def set_simulation(on: bool) -> None:
    """Tryb symulacji — brak sprzętu, wartości losowe (do nauki obsługi GUI)."""
    global SIMULATE
    SIMULATE = on


# ── podpowiedzi wielokrotnego użytku ─────────────────────────────────────────
HINT_I2C = [
    "Włącz I2C: sudo raspi-config → Interface Options → I2C → Yes, potem reboot",
    "Sprawdź czy urządzenie jest widoczne: i2cdetect -y 1",
    "SDA = pin 3 (GPIO2), SCL = pin 5 (GPIO3), VCC = 3.3 V (pin 1), GND = pin 6",
    "Rezystory podciągające są już na modułach — nie dodawaj własnych",
]
HINT_SPI = [
    "Włącz SPI: sudo raspi-config → Interface Options → SPI → Yes, potem reboot",
    "Sprawdź urządzenia: ls /dev/spidev*",
]
HINT_UART = [
    "sudo raspi-config → Interface Options → Serial Port:",
    "   konsola logowania przez port szeregowy: NIE",
    "   sprzętowy port szeregowy włączony: TAK",
    "Krzyżowo: RPi TX (pin 8) → RX urządzenia, RPi RX (pin 10) ← TX urządzenia",
]
HINT_GPIO_PI5 = [
    "Na Raspberry Pi 5 stare RPi.GPIO nie działa — potrzebna nakładka lgpio:",
    "   sudo apt remove python3-rpi.gpio && sudo apt install python3-rpi-lgpio",
]


# ── pomocnicze ───────────────────────────────────────────────────────────────
def _missing(exc: BaseException, hints: list[str]) -> Result:
    return Result(MISSING, f"Brak biblioteki / interfejsu: {exc}", hints=hints)


def _fail(exc: BaseException, hints: list[str]) -> Result:
    return Result(FAIL, f"{type(exc).__name__}: {exc}", hints=hints)


def _gpio_hints(extra: list[str] | None = None) -> list[str]:
    hints = list(extra or [])
    if is_pi5():
        hints += HINT_GPIO_PI5
    else:
        hints += ["pip install RPi.GPIO   (na RPi 5: sudo apt install python3-rpi-lgpio)"]
    return hints


def _altitude_m(pressure_hpa: float) -> float:
    """Wysokość barometryczna wg modelu ISA (ten sam wzór co w locie)."""
    if pressure_hpa <= 0:
        return 0.0
    return 44330.0 * (1.0 - (pressure_hpa / 1013.25) ** 0.1903)


def _jitter(base: float, spread: float, nd: int = 2) -> float:
    return round(base + random.uniform(-spread, spread), nd)


def _dev_exists(path: str) -> bool:
    return os.path.exists(path)


# ── I2C: skan magistrali ─────────────────────────────────────────────────────
I2C_KNOWN = {
    0x40: "INA219 (prąd/napięcie baterii)",
    0x41: "INA219 — adres alternatywny",
    0x4A: "BNO085 (IMU 9-DOF)",
    0x4B: "BNO085 — adres alternatywny",
    0x76: "BME280 (temperatura/wilgotność/ciśnienie)",
    0x77: "MS5611 (ciśnienie precyzyjne)",
}


def test_i2c_scan() -> Result:
    """Odpowiednik i2cdetect -y 1 — pokazuje wszystkie układy na magistrali."""
    if SIMULATE:
        found = [0x40, 0x4A, 0x76, 0x77]
        return Result(OK, f"Symulacja: znaleziono {len(found)} układy na I2C-1",
                      {f"0x{a:02X}": I2C_KNOWN.get(a, "nieznany") for a in found})

    if not _dev_exists("/dev/i2c-1"):
        return Result(MISSING, "Brak /dev/i2c-1 — magistrala I2C jest wyłączona",
                      hints=HINT_I2C)
    try:
        import smbus2
    except ImportError as e:
        return _missing(e, ["pip install smbus2", "lub: sudo apt install python3-smbus2"])

    found: list[int] = []
    try:
        bus = smbus2.SMBus(1)
    except OSError as e:
        return _fail(e, HINT_I2C)
    try:
        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                found.append(addr)
                continue
            except OSError:
                pass
            # układy tylko-do-zapisu nie odpowiadają na odczyt (tak samo robi i2cdetect)
            if 0x30 <= addr <= 0x37 or 0x50 <= addr <= 0x5F:
                continue
            try:
                bus.write_quick(addr)
                found.append(addr)
            except OSError:
                pass
    finally:
        bus.close()

    values = {f"0x{a:02X}": I2C_KNOWN.get(a, "nieznany układ") for a in found}
    if not found:
        return Result(FAIL, "Magistrala I2C pusta — żaden układ nie odpowiada",
                      hints=HINT_I2C + ["Sprawdź zasilanie modułów (3.3 V, nie 5 V!)"])
    expected = {0x76: "BME280", 0x77: "MS5611", 0x4A: "BNO085", 0x40: "INA219"}
    brak = [n for a, n in expected.items() if a not in found]
    if brak:
        return Result(WARN, f"Znaleziono {len(found)} adresów, brakuje: {', '.join(brak)}",
                      values,
                      ["Każdy brakujący układ sprawdź osobno na liście po lewej"] + HINT_I2C)
    return Result(OK, f"Wszystkie 4 układy I2C odpowiadają ({len(found)} adresów)", values)


# ── BME280 ───────────────────────────────────────────────────────────────────
def test_bme280() -> Result:
    addr = air("BME280_ADDR", 0x76)
    if SIMULATE:
        t, h, p = _jitter(21.4, 0.3), _jitter(43.0, 2.0), _jitter(1002.7, 0.4)
        return Result(OK, "Symulacja — czujnik odpowiada", {
            "Temperatura": f"{t} °C", "Wilgotność": f"{h} %", "Ciśnienie": f"{p} hPa",
            "Wysokość (z ciśnienia)": f"{_altitude_m(p):.0f} m"})
    try:
        mod = load_repo_module("air_sensor_bme280", "rpi-air/sensors/bme280.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install smbus2 bme280", "lub: sudo apt install python3-smbus2"])
    try:
        sensor = mod.Bme280Sensor(addr, 1)
        sensor.read()          # pierwszy odczyt tylko budzi przetwornik
        time.sleep(0.2)
        d = sensor.read()
    except Exception as e:
        return _fail(e, [f"Czujnik nie odpowiada pod adresem 0x{addr:02X}",
                         "Część modułów ma adres 0x77 (zworka SDO/ADDR)"] + HINT_I2C)

    values = {
        "Temperatura": f"{d.temperature_c} °C",
        "Wilgotność": f"{d.humidity_pct} %",
        "Ciśnienie": f"{d.pressure_hpa} hPa",
        "Wysokość (z ciśnienia)": f"{_altitude_m(d.pressure_hpa):.0f} m",
    }
    if not (-60 <= d.temperature_c <= 85) or not (200 <= d.pressure_hpa <= 1200):
        return Result(WARN, "Czujnik odpowiada, ale wartości są poza sensownym zakresem",
                      values, ["Możliwy zły adres I2C albo uszkodzony moduł",
                               "Sprawdź czy pod tym adresem nie siedzi inny układ"])
    return Result(OK, "Odczyt poprawny", values)


# ── MS5611 ───────────────────────────────────────────────────────────────────
def test_ms5611() -> Result:
    addr = air("MS5611_ADDR", 0x77)
    if SIMULATE:
        p = _jitter(1002.9, 0.3)
        return Result(OK, "Symulacja — czujnik odpowiada", {
            "Ciśnienie": f"{p} hPa", "Temperatura": f"{_jitter(21.8, 0.2)} °C",
            "Wysokość": f"{_altitude_m(p):.1f} m"})
    try:
        mod = load_repo_module("air_sensor_ms5611", "rpi-air/sensors/ms5611.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install smbus2"])
    try:
        sensor = mod.Ms5611Sensor(addr, 1)
        d = sensor.read()
    except Exception as e:
        return _fail(e, [f"Brak odpowiedzi pod adresem 0x{addr:02X}",
                         "MS5611 na module GY-63/GY-86 bywa pod 0x76 (pin CSB)"] + HINT_I2C)

    values = {
        "Ciśnienie": f"{d.pressure_hpa} hPa",
        "Temperatura": f"{d.temperature_c} °C",
        "Wysokość": f"{d.altitude_m} m",
    }
    if not (200 <= d.pressure_hpa <= 1200):
        return Result(WARN, "Czujnik odpowiada, ale ciśnienie jest poza zakresem", values,
                      ["Sprawdź kalibrację PROM — możliwe zakłócenia na I2C",
                       "Zwolnij magistralę: dtparam=i2c_arm_baudrate=100000"])
    if abs(d.pressure_hpa - 1013.25) > 200:
        return Result(WARN, "Ciśnienie mocno odbiega od normalnego (1013 hPa)", values)
    return Result(OK, "Odczyt poprawny", values)


# ── BNO085 (IMU) ─────────────────────────────────────────────────────────────
def test_bno085() -> Result:
    if SIMULATE:
        return Result(OK, "Symulacja — IMU odpowiada", {
            "Roll": f"{_jitter(1.2, 0.8)} °", "Pitch": f"{_jitter(-0.7, 0.8)} °",
            "Yaw": f"{_jitter(128.4, 1.5)} °",
            "Akcelerometr":
                f"x={_jitter(0.1, 0.2)} y={_jitter(0.0, 0.2)} z={_jitter(9.81, 0.1)} m/s²",
            "Wektor przyspieszenia": "9.81 m/s² (≈ 1 g — czujnik leży poziomo)"})
    try:
        mod = load_repo_module("air_sensor_bno085", "rpi-air/sensors/bno085.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install adafruit-circuitpython-bno08x adafruit-blinka"])
    try:
        sensor = mod.Bno085Sensor()
        time.sleep(0.5)        # BNO085 potrzebuje chwili po włączeniu raportów
        d = sensor.read()
    except Exception as e:
        return _fail(e, [
            "BNO085 rozciąga zegar I2C — przy błędach zwolnij magistralę:",
            "   /boot/firmware/config.txt →  dtparam=i2c_arm_baudrate=50000",
            "Adres domyślny 0x4A (0x4B gdy pin ADR podciągnięty do 3.3 V)",
        ] + HINT_I2C)

    g = math.sqrt(d.accel_x ** 2 + d.accel_y ** 2 + d.accel_z ** 2)
    values = {
        "Roll": f"{d.roll_deg} °", "Pitch": f"{d.pitch_deg} °", "Yaw": f"{d.yaw_deg} °",
        "Akcelerometr": f"x={d.accel_x} y={d.accel_y} z={d.accel_z} m/s²",
        "Wektor przyspieszenia": f"{g:.2f} m/s² (powinno być ~9.81)",
    }
    if g < 5 or g > 15:
        return Result(WARN, "IMU odpowiada, ale przyspieszenie ≠ 1 g", values,
                      ["Połóż czujnik nieruchomo i powtórz test",
                       "Jeśli dalej źle — czujnik nie zdążył się zainicjalizować"])
    if d.roll_deg == 0 and d.pitch_deg == 0 and d.yaw_deg == 0:
        return Result(WARN, "IMU odpowiada, ale nie ma jeszcze wektora obrotu", values,
                      ["Poczekaj 2-3 s i powtórz test (fuzja czujników się kalibruje)"])
    return Result(OK, "Odczyt poprawny", values)


# ── INA219 (bateria) ─────────────────────────────────────────────────────────
def test_ina219() -> Result:
    addr = air("INA219_ADDR", 0x40)
    shunt = air("INA219_SHUNT_OHMS", 0.1)
    if SIMULATE:
        v, i = _jitter(7.82, 0.05, 3), _jitter(430.0, 25.0)
        return Result(OK, "Symulacja — czujnik odpowiada", {
            "Napięcie": f"{v} V", "Prąd": f"{i} mA", "Moc": f"{round(v * i, 1)} mW"})
    try:
        mod = load_repo_module("air_sensor_ina219", "rpi-air/sensors/ina219.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install pi-ina219"])
    try:
        sensor = mod.Ina219Sensor(shunt, addr)
        d = sensor.read()
    except Exception as e:
        return _fail(e, [f"Brak odpowiedzi pod adresem 0x{addr:02X}",
                         "Adres zależy od zworek A0/A1 (0x40…0x45)"] + HINT_I2C)

    values = {
        "Napięcie": f"{d.voltage_v} V", "Prąd": f"{d.current_ma} mA",
        "Moc": f"{d.power_mw} mW", "Bocznik": f"{shunt} Ω",
    }
    if d.voltage_v < 1.0:
        return Result(WARN, "Układ odpowiada, ale nie widzi napięcia na wejściu", values,
                      ["Bateria idzie przez zaciski Vin+ / Vin− (bocznik), nie przez VCC",
                       "VCC modułu (3.3 V) zasila tylko elektronikę pomiarową"])
    if d.current_ma < 1.0:
        return Result(WARN, "Napięcie OK, ale prąd ≈ 0 — brak obciążenia?", values,
                      ["Sprawdź czy odbiornik jest podłączony za bocznikiem (Vin−)"])
    return Result(OK, "Odczyt poprawny", values)


# ── HX711 (tensometry) ───────────────────────────────────────────────────────
HX711_LABELS = ["przód lewy", "przód prawy", "tył lewy", "tył prawy"]
_HX711_DEFAULT = [{"dt": 16, "sck": 21}, {"dt": 19, "sck": 20},
                  {"dt": 12, "sck": 13}, {"dt": 24, "sck": 25}]


def hx711_pins(index: int) -> dict:
    pins = air("HX711_SENSORS", _HX711_DEFAULT)
    return pins[index] if index < len(pins) else _HX711_DEFAULT[index]


def test_hx711(index: int) -> Result:
    pins = hx711_pins(index)
    ref = air("HX711_REFERENCE_UNIT", 1.0)
    dt, sck = pins["dt"], pins["sck"]
    if SIMULATE:
        raws = [random.randint(128_000, 128_400) for _ in range(5)]
        return Result(OK, "Symulacja — przetwornik odpowiada", {
            "Kanał": f"#{index} ({HX711_LABELS[index]})",
            "Surowe ADC": f"min {min(raws)}  max {max(raws)}  rozrzut {max(raws) - min(raws)}",
            "Waga": f"{_jitter(0.0, 3.0, 1)} g", "reference_unit": f"{ref}"})
    try:
        mod = load_repo_module("air_sensor_hx711", "rpi-air/sensors/hx711.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, _gpio_hints())
    sensor = None
    try:
        sensor = mod.Hx711Sensor(dt, sck, ref)
        raws = [sensor._read_raw() for _ in range(5)]   # surowe ADC — do diagnostyki
        grams = sensor.read().strain_g
    except TimeoutError:
        return Result(FAIL, "HX711 nie zgłasza gotowości (linia DT stale w stanie wysokim)",
                      hints=[f"DT = GPIO{dt}, SCK = GPIO{sck}",
                             "Sprawdź zasilanie modułu: VCC = 3.3 V, GND wspólna z RPi",
                             "Zamienione DT ↔ SCK to najczęstszy błąd",
                             "Bez podłączonego mostka tensometrycznego HX711 też milczy"])
    except Exception as e:
        return _fail(e, _gpio_hints([f"DT = GPIO{dt}, SCK = GPIO{sck}"]))
    finally:
        if sensor is not None:
            try:
                sensor.close()
            except Exception:
                pass

    spread = max(raws) - min(raws)
    values = {
        "Kanał": f"#{index} ({HX711_LABELS[index]})",
        "Piny": f"DT = GPIO{dt}, SCK = GPIO{sck}",
        "Surowe ADC": f"min {min(raws)}  max {max(raws)}  rozrzut {spread}",
        "Waga (po tarowaniu)": f"{grams} g",
        "reference_unit": f"{ref}",
    }
    if all(r in (0, -1, 0x7FFFFF, -0x800000) for r in raws):
        return Result(FAIL, "Przetwornik zwraca wartość skrajną — brak sygnału z mostka", values,
                      ["Sprawdź tensometr: E+ / E− (zasilanie mostka), A+ / A− (sygnał)",
                       "Zamienione A+ / A− dają ujemne wskazania — to nie awaria"])
    if spread == 0:
        return Result(WARN, "Odczyt się nie zmienia — podejrzanie stabilnie", values,
                      ["Naciśnij lekko tensometr i powtórz test — wartość musi drgnąć"])
    if spread > 50_000:
        return Result(WARN, "Bardzo duży szum odczytu", values,
                      ["Skróć przewody DT/SCK, odsuń je od przewodów zasilania",
                       "Sprawdź wspólną masę modułu i RPi"])
    return Result(OK, "Przetwornik odpowiada, odczyt stabilny", values)


# ── GPS NEO-M8N ──────────────────────────────────────────────────────────────
GPS_PORTS = ["/dev/ttyAMA0", "/dev/serial0", "/dev/ttyUSB0", "/dev/ttyACM0"]


def test_gps(seconds: float = 5.0) -> Result:
    if SIMULATE:
        return Result(OK, "Symulacja — odbiornik nadaje NMEA", {
            "Port": "/dev/ttyUSB0 @ 9600",
            "Zdania NMEA": "37 w 5 s",
            "Fix": "3D",
            "Satelity": f"{random.randint(7, 12)}",
            "Pozycja": f"{_jitter(52.2297, 0.001, 5)}, {_jitter(21.0122, 0.001, 5)}",
            "Wysokość": f"{_jitter(112.0, 2.0, 1)} m"})
    try:
        import serial
    except ImportError as e:
        return _missing(e, ["pip install pyserial pynmea2"])
    try:
        import pynmea2
    except ImportError:
        pynmea2 = None

    ports = [p for p in GPS_PORTS if _dev_exists(p)]
    if not ports:
        return Result(MISSING, "Nie znaleziono żadnego portu szeregowego",
                      hints=["Przejściówka USB-TTL → /dev/ttyUSB0",
                             "Wbudowany UART RPi → /dev/ttyAMA0"] + HINT_UART)

    last_err = None
    for port in ports:
        try:
            ser = serial.Serial(port, 9600, timeout=1)
        except Exception as e:
            last_err = e
            continue
        sentences, gga, fix, sats, lat, lon, alt = 0, 0, False, 0, None, None, None
        deadline = time.time() + seconds
        try:
            while time.time() < deadline:
                raw = ser.readline().decode("ascii", errors="replace").strip()
                if not raw.startswith("$"):
                    continue
                sentences += 1
                if pynmea2 is None:
                    continue
                try:
                    msg = pynmea2.parse(raw)
                except Exception:
                    continue
                if isinstance(msg, pynmea2.GGA):
                    gga += 1
                    sats = int(msg.num_sats or 0)
                    fix = (msg.gps_qual or 0) > 0
                    if fix:
                        lat, lon = msg.latitude, msg.longitude
                        alt = float(msg.altitude or 0)
        finally:
            ser.close()

        if sentences == 0:
            last_err = OSError(f"{port}: cisza na porcie")
            continue

        values = {
            "Port": f"{port} @ 9600 baud",
            "Zdania NMEA": f"{sentences} w {seconds:.0f} s",
            "Zdania GGA": f"{gga}",
            "Fix": "TAK" if fix else "NIE (brak pozycji)",
            "Satelity": f"{sats}",
        }
        if fix:
            values["Pozycja"] = f"{lat:.5f}, {lon:.5f}"
            values["Wysokość"] = f"{alt:.1f} m"
            return Result(OK, "Odbiornik działa i ma fix", values)
        return Result(WARN, "Odbiornik nadaje NMEA, ale nie ma jeszcze pozycji", values,
                      ["Wynieś antenę pod otwarte niebo — w budynku fix nie złapie",
                       "Zimny start NEO-M8N to nawet 60-90 s",
                       "Migająca dioda na module = fix złapany"])

    return Result(FAIL, f"Brak danych NMEA (sprawdzone porty: {', '.join(ports)})",
                  hints=[f"Ostatni błąd: {last_err}",
                         "GPS TX → RPi RX (pin 10, GPIO15) — sygnał idzie w jedną stronę",
                         "Prędkość NEO-M8N: 9600 baud (domyślnie)",
                         "W locie GPS jest podłączony do ESP32 (GPIO4), nie do RPi —",
                         "   ten test służy do sprawdzenia modułu na stole"] + HINT_UART)


# ── LoRa SX1278 (SPI) ────────────────────────────────────────────────────────
_SX_REG_OP_MODE = 0x01
_SX_REG_FRF_MSB = 0x06
_SX_REG_MODEM_CONFIG1 = 0x1D
_SX_REG_MODEM_CONFIG2 = 0x1E
_SX_REG_MODEM_CONFIG3 = 0x26
_SX_REG_FIFO = 0x00
_SX_REG_FIFO_ADDR_PTR = 0x0D
_SX_REG_FIFO_RX_BASE = 0x0F
_SX_REG_FIFO_RX_CURRENT = 0x10
_SX_REG_IRQ_FLAGS = 0x12
_SX_REG_RX_NB_BYTES = 0x13
_SX_REG_PKT_SNR = 0x19
_SX_REG_PKT_RSSI = 0x1A
_SX_REG_SYNC_WORD = 0x39
_SX_REG_DIO_MAPPING1 = 0x40
_SX_REG_VERSION = 0x42
_SX_MODE_SLEEP, _SX_MODE_STDBY, _SX_MODE_RX_CONT = 0x00, 0x01, 0x05
_SX_MODE_LORA = 0x80
_SX_IRQ_RX_DONE, _SX_IRQ_CRC_ERR = 0x40, 0x20

_BW_MAP = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4,
           41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9}


def _sx_open():
    """Otwiera SPI do SX1278 wg rpi-ground/config.py. Zwraca (spi, opis)."""
    import spidev
    bus = ground("LORA_SPI_BUS", 0)
    cs = ground("LORA_SPI_CS", 0)
    spi = spidev.SpiDev()
    spi.open(bus, cs)
    spi.max_speed_hz = 1_000_000
    return spi, f"/dev/spidev{bus}.{cs}"


def _sx_read(spi, reg: int) -> int:
    return spi.xfer2([reg & 0x7F, 0x00])[1]


def _sx_write(spi, reg: int, val: int) -> None:
    spi.xfer2([reg | 0x80, val & 0xFF])


def test_lora_present() -> Result:
    """Sprawdza obecność SX1278 na SPI — rejestr wersji musi zwrócić 0x12."""
    if SIMULATE:
        return Result(OK, "Symulacja — SX1278 odpowiada", {
            "Port SPI": "/dev/spidev0.0", "RegVersion": "0x12 (SX1276/77/78)",
            "Częstotliwość": f"{ground('LORA_FREQ', 433.0)} MHz",
            "SF / BW / CR": "SF10 / 125 kHz / 4:5"})
    if not any(_dev_exists(f"/dev/spidev0.{i}") or _dev_exists(f"/dev/spidev1.{i}")
               for i in range(3)):
        return Result(MISSING, "Brak urządzeń /dev/spidev* — SPI jest wyłączone",
                      hints=HINT_SPI)
    try:
        spi, portname = _sx_open()
    except ImportError as e:
        return _missing(e, ["pip install spidev"] + HINT_SPI)
    except Exception as e:
        return _fail(e, HINT_SPI)
    try:
        ver = _sx_read(spi, _SX_REG_VERSION)
        mode = _sx_read(spi, _SX_REG_OP_MODE)
    except Exception as e:
        return _fail(e, HINT_SPI)
    finally:
        spi.close()

    values = {
        "Port SPI": portname,
        "RegVersion (0x42)": f"0x{ver:02X}",
        "RegOpMode (0x01)": f"0x{mode:02X}",
        "Częstotliwość z configu": f"{ground('LORA_FREQ', 433.0)} MHz",
        "DIO0": f"GPIO{ground('LORA_DIO0_PIN', 25)}",
    }
    if ver == 0x12:
        return Result(OK, "SX1278 odpowiada poprawnie (0x12)", values)
    if ver in (0x00, 0xFF):
        return Result(FAIL, f"Brak odpowiedzi modułu (0x{ver:02X})", values,
                      ["Sprawdź MISO/MOSI — zamiana tych dwóch daje dokładnie ten objaw",
                       "NSS/CS musi iść do CE0 (pin 24), RST podciągnięty lub do GPIO",
                       "Moduł zasilany 3.3 V — 5 V go zniszczy",
                       "Antena MUSI być podłączona przed nadawaniem"] + HINT_SPI)
    return Result(WARN, f"Odpowiedź jest, ale wersja nietypowa: 0x{ver:02X}", values,
                  ["SX1276/77/78 zwracają 0x12 — inna wartość = inny układ lub zakłócenia"])


def test_lora_rx(seconds: float = 12.0) -> Result:
    """Nasłuch pakietu z balonu — ustawienia z rpi-ground/config.py."""
    freq = ground("LORA_FREQ", 433.0)
    sf = ground("LORA_SF", 10)
    bw = ground("LORA_BW", 125000)
    cr = ground("LORA_CR", 5)
    if SIMULATE:
        return Result(OK, "Symulacja — odebrano pakiet", {
            "Częstotliwość": f"{freq} MHz", "SF / BW / CR": f"SF{sf} / {bw // 1000} kHz / 4:{cr}",
            "RSSI": f"{random.randint(-115, -60)} dBm", "SNR": f"{_jitter(8.0, 3.0, 1)} dB",
            "Długość pakietu": f"{random.randint(80, 200)} B"})
    try:
        spi, portname = _sx_open()
    except ImportError as e:
        return _missing(e, ["pip install spidev"] + HINT_SPI)
    except Exception as e:
        return _fail(e, HINT_SPI)
    try:
        if _sx_read(spi, _SX_REG_VERSION) != 0x12:
            return Result(FAIL, "SX1278 nie odpowiada — najpierw zrób test obecności modułu",
                          hints=HINT_SPI)
        # konfiguracja identyczna jak w rpi-ground/radio/lora_rx.py
        _sx_write(spi, _SX_REG_OP_MODE, _SX_MODE_LORA | _SX_MODE_SLEEP)
        time.sleep(0.01)
        frf = int((freq * 1e6) / 61.03515625)
        _sx_write(spi, _SX_REG_FRF_MSB, (frf >> 16) & 0xFF)
        _sx_write(spi, _SX_REG_FRF_MSB + 1, (frf >> 8) & 0xFF)
        _sx_write(spi, _SX_REG_FRF_MSB + 2, frf & 0xFF)
        _sx_write(spi, _SX_REG_MODEM_CONFIG1, (_BW_MAP.get(bw, 7) << 4) | ((cr - 4) << 1))
        _sx_write(spi, _SX_REG_MODEM_CONFIG2, (sf << 4) | 0x04)
        _sx_write(spi, _SX_REG_MODEM_CONFIG3, 0x04)
        _sx_write(spi, _SX_REG_SYNC_WORD, 0x12)
        _sx_write(spi, _SX_REG_FIFO_RX_BASE, 0x00)
        _sx_write(spi, _SX_REG_FIFO_ADDR_PTR, 0x00)
        _sx_write(spi, _SX_REG_DIO_MAPPING1, 0x00)
        _sx_write(spi, _SX_REG_IRQ_FLAGS, 0xFF)
        _sx_write(spi, _SX_REG_OP_MODE, _SX_MODE_LORA | _SX_MODE_RX_CONT)

        deadline = time.time() + seconds
        while time.time() < deadline:
            irq = _sx_read(spi, _SX_REG_IRQ_FLAGS)
            if irq & _SX_IRQ_RX_DONE:
                crc_err = bool(irq & _SX_IRQ_CRC_ERR)
                length = _sx_read(spi, _SX_REG_RX_NB_BYTES)
                _sx_write(spi, _SX_REG_FIFO_ADDR_PTR, _sx_read(spi, _SX_REG_FIFO_RX_CURRENT))
                payload = bytes(_sx_read(spi, _SX_REG_FIFO) for _ in range(length))
                rssi = _sx_read(spi, _SX_REG_PKT_RSSI) - 157
                snr_raw = _sx_read(spi, _SX_REG_PKT_SNR)
                snr = (snr_raw - 256 if snr_raw > 127 else snr_raw) / 4.0
                _sx_write(spi, _SX_REG_IRQ_FLAGS, 0xFF)
                preview = payload[:60].decode("utf-8", errors="replace")
                values = {
                    "Częstotliwość": f"{freq} MHz",
                    "SF / BW / CR": f"SF{sf} / {bw // 1000} kHz / 4:{cr}",
                    "RSSI": f"{rssi} dBm", "SNR": f"{snr:.1f} dB",
                    "Długość pakietu": f"{length} B", "Początek pakietu": preview,
                }
                if crc_err:
                    return Result(WARN, "Pakiet odebrany, ale z błędem CRC", values,
                                  ["Sygnał za słaby albo nadajnik ma inne SF/BW/CR"])
                return Result(OK, "Pakiet odebrany poprawnie", values)
            time.sleep(0.02)
    except Exception as e:
        return _fail(e, HINT_SPI)
    finally:
        try:
            _sx_write(spi, _SX_REG_OP_MODE, _SX_MODE_LORA | _SX_MODE_STDBY)
            spi.close()
        except Exception:
            pass

    return Result(WARN, f"Cisza w eterze przez {seconds:.0f} s — brak pakietów", {
        "Częstotliwość": f"{freq} MHz",
        "SF / BW / CR": f"SF{sf} / {bw // 1000} kHz / 4:{cr}",
    }, ["Nadajnik (ESP32 na balonie) musi być włączony — nadaje co ~5 s",
        "Obie strony muszą mieć TE SAME: częstotliwość, SF, BW, CR i sync word 0x12",
        "Sprawdź antenę 433 MHz po obu stronach"])


# ── RTL-SDR (odbiornik HF) ───────────────────────────────────────────────────
def test_rtlsdr() -> Result:
    freq = air("SDR_TARGET_FREQ", 7_100_000)
    if SIMULATE:
        return Result(OK, "Symulacja — dongle odpowiada", {
            "Częstotliwość": f"{freq / 1e6:.3f} MHz",
            "Moc nośnej": f"{_jitter(-42.0, 4.0, 1)} dBFS",
            "Próbkowanie": f"{air('SDR_SAMPLE_RATE', 250000) / 1000:.0f} kHz"})
    try:
        mod = load_repo_module("air_sdr", "rpi-air/hardware/sdr_receiver.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install pyrtlsdr numpy",
                            "sudo apt install rtl-sdr librtlsdr-dev"])
    if not getattr(mod, "_AVAILABLE", True):
        return Result(MISSING, "Brak pyrtlsdr / numpy — sterownik SDR wyłączony",
                      hints=["pip install pyrtlsdr numpy",
                             "sudo apt install rtl-sdr librtlsdr-dev"])
    sdr = None
    try:
        sdr = mod.SdrReceiver(
            target_freq_hz=freq,
            sample_rate=air("SDR_SAMPLE_RATE", 250_000),
            gain=air("SDR_GAIN", "auto"),
            freq_correction=air("SDR_FREQ_CORRECTION", 0),
            num_samples=64 * 1024,          # krótszy pomiar niż w locie — test ma być szybki
            bin_window=air("SDR_BIN_WINDOW", 15),
        )
        if not sdr.available:
            return Result(FAIL, "Dongle RTL-SDR nie został otwarty", hints=[
                "Sprawdź czy jest widoczny: lsusb | grep -i rtl",
                "Zablokuj sterownik DVB: echo 'blacklist dvb_usb_rtl28xxu' | "
                "sudo tee /etc/modprobe.d/blacklist-rtl.conf",
                "Test poza GUI: rtl_test -t",
                "sudo apt install rtl-sdr librtlsdr-dev; pip install pyrtlsdr numpy"])
        dbfs = sdr.measure()
    except Exception as e:
        return _fail(e, ["lsusb | grep -i rtl", "rtl_test -t"])
    finally:
        if sdr is not None:
            try:
                sdr.close()
            except Exception:
                pass

    values = {
        "Częstotliwość": f"{freq / 1e6:.3f} MHz",
        "Moc nośnej": f"{dbfs:.1f} dBFS",
        "Próbkowanie": f"{air('SDR_SAMPLE_RATE', 250000) / 1000:.0f} kHz",
    }
    if dbfs == -999.0:
        return Result(FAIL, "Pomiar nieudany", values, ["Powtórz test", "rtl_test -t"])
    if dbfs < -80:
        return Result(WARN, "Dongle działa, ale nie widzi nośnej (bardzo słaby sygnał)", values,
                      ["Włącz nadajnik HF na stacji naziemnej",
                       "Sprawdź antenę w gnieździe SMA",
                       "Poziom ok. -80 dBFS to szum własny odbiornika"])
    return Result(OK, "Dongle działa i widzi sygnał", values)


# ── Kamera CSI ───────────────────────────────────────────────────────────────
def test_camera() -> Result:
    if SIMULATE:
        return Result(OK, "Symulacja — kamera odpowiada", {
            "Model": "imx708 (Camera Module 3)", "Zdjęcie testowe": "640×480 RGB",
            "Katalog nagrań": air("CAM_RECORD_DIR", "/home/pi/stratosteam-video")})
    try:
        from picamera2 import Picamera2
    except ImportError:
        # picamera2 nie ma → spróbuj narzędzia systemowego
        try:
            out = subprocess.run(["rpicam-hello", "--list-cameras"],
                                 capture_output=True, text=True, timeout=10)
            txt = (out.stdout + out.stderr).strip()
            if "Available cameras" in txt:
                return Result(WARN, "Kamerę widzi system, ale brak biblioteki picamera2",
                              {"rpicam-hello": txt.splitlines()[0] if txt else ""},
                              ["sudo apt install python3-picamera2"])
            return Result(FAIL, "System nie widzi żadnej kamery",
                          hints=["Taśma CSI w złączu CAM0, styki w stronę radiatora",
                                 "Sprawdź: rpicam-hello --list-cameras"])
        except Exception as e:
            return _missing(e, ["sudo apt install python3-picamera2 rpicam-apps"])

    cam = None
    try:
        cam = Picamera2()
        model = cam.camera_properties.get("Model", "nieznany")
        cam.configure(cam.create_still_configuration(main={"size": (640, 480)}))
        cam.start()
        time.sleep(0.6)
        frame = cam.capture_array()
        cam.stop()
    except Exception as e:
        return _fail(e, ["Taśma CSI musi być w złączu CAM0 (przy złączu zasilania)",
                         "Styki taśmy w stronę radiatora/HDMI",
                         "Sprawdź: rpicam-hello --list-cameras",
                         "Jeśli kamera jest zajęta przez inny program — zatrzymaj usługę:",
                         "   sudo systemctl stop stratosteam-air"])
    finally:
        if cam is not None:
            try:
                cam.close()
            except Exception:
                pass

    rec_dir = air("CAM_RECORD_DIR", "/home/pi/stratosteam-video")
    values = {
        "Model": str(model),
        "Zdjęcie testowe": f"{frame.shape[1]}×{frame.shape[0]}",
        "Katalog nagrań": rec_dir,
        "Katalog istnieje": "tak" if os.path.isdir(rec_dir) else "NIE — zostanie utworzony",
    }
    if float(frame.mean()) < 2.0:
        return Result(WARN, "Kamera działa, ale obraz jest praktycznie czarny", values,
                      ["Zdejmij folię ochronną z obiektywu", "Sprawdź oświetlenie"])
    return Result(OK, "Kamera działa, zdjęcie wykonane", values)


# ── ESP32-CAM: zasilanie przez MOSFET ────────────────────────────────────────
def test_espcam_power() -> Result:
    pin = air("ESPCAM_PWR_PIN", 17)
    if SIMULATE:
        return Result(OK, "Symulacja — kanał zasilania przełączony", {
            "Kamera": f"GPIO{pin}: włączona → wyłączona OK"})
    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        return _missing(e, _gpio_hints())
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.8)
        high = GPIO.input(pin)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.2)
        low = GPIO.input(pin)
    except Exception as e:
        return _fail(e, _gpio_hints())
    finally:
        try:
            GPIO.cleanup(pin)
        except Exception:
            pass

    values = {"Kamera": f"GPIO{pin}: HIGH={high}, LOW={low}"}
    if not (high == 1 and low == 0):
        return Result(FAIL, "Pin zasilania kamery nie przełącza się", values,
                      ["Zwarcie na bramce MOSFET-a albo pin zajęty przez inny program"])
    return Result(INFO, "Pin sterujący przełącza się poprawnie — sprawdź diodę kamery", values,
                  ["Test podaje stan tylko na GPIO — czy kamera faktycznie wstała,",
                   "   widać po jej diodzie lub w teście statusu ESP32-CAM",
                   "HIGH na GPIO = MOSFET otwarty = kamera zasilona"])


# ── ESP32-CAM: status po UART (pigpio bit-bang) ──────────────────────────────
def test_espcam_status(seconds: float = 8.0) -> Result:
    pin = air("ESPCAM_STATUS_PIN", 4)
    baud = air("ESPCAM_STATUS_BAUD", 115200)
    if SIMULATE:
        return Result(OK, "Symulacja — kamera raportuje status", {
            "Stan": "OK, nagrywa",
            "Klatki": f"{random.randint(900, 4000)}",
            "Wolne na karcie": f"{random.randint(3000, 12000)} MB"})
    try:
        mod = load_repo_module("air_espcam_monitor", "rpi-air/hardware/espcam_monitor.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["sudo apt install pigpio python3-pigpio",
                            "sudo systemctl enable --now pigpiod"])
    mon = None
    try:
        mon = mod.EspCamMonitor(pin, baud)
        if getattr(mon, "_pi", None) is None:
            return Result(MISSING, "pigpio niedostępne (demon nie działa lub RPi 5)", hints=[
                "Uruchom demona: sudo systemctl enable --now pigpiod",
                "UWAGA: pigpio nie wspiera Raspberry Pi 5 — na RPi 5 ten odczyt",
                "   trzeba przepisać na lgpio albo sprzętowy UART",
                f"Pin statusu: GPIO{pin} @ {baud} baud"])
        time.sleep(seconds)     # kamera raportuje co ~5 s
        ok, rec, frames, free_mb = (list(mon.compact()) + [0, 0, 0, 0])[:4]
    except Exception as e:
        return _fail(e, ["sudo systemctl enable --now pigpiod",
                         "pigpio nie działa na Raspberry Pi 5"])
    finally:
        if mon is not None:
            try:
                mon.stop()
            except Exception:
                pass

    values = {
        "Pin": f"GPIO{pin} @ {baud} baud",
        "Stan": "OK" if ok else "brak danych",
        "Nagrywanie": "tak" if rec else "nie",
        "Klatki": f"{frames}",
        "Wolne na karcie": f"{free_mb} MB",
    }
    if not ok:
        return Result(FAIL, "Kamera nie przysłała statusu", values,
                      ["Najpierw włącz zasilanie kamery (test zasilania ESP32-CAM)",
                       f"ESP32-CAM GPIO1 (U0TX) → RPi GPIO{pin} (pin 7)",
                       f"Prędkość musi być {baud} baud (tak nadaje espcam/src/main.cpp)",
                       "Masa ESP32-CAM i RPi musi być wspólna",
                       "Kamera nadaje linie z prefiksem $S — reszta jest ignorowana"])
    if free_mb < 500:
        return Result(WARN, "Kamera działa, ale na karcie zostało mało miejsca", values,
                      ["Zgraj nagrania i sformatuj kartę przed startem"])
    return Result(OK, "Kamera raportuje status", values)


# ── UART RPi5 ↔ ESP32-S3 ─────────────────────────────────────────────────────
def test_esp_uart(seconds: float = 6.0) -> Result:
    port = air("ESP_UART_PORT", "/dev/ttyAMA0")
    baud = air("ESP_UART_BAUD", 115200)
    if SIMULATE:
        return Result(OK, "Symulacja — ESP32 odpowiada", {
            "Port": f"{port} @ {baud}", "Odebrane linie": "2",
            "Ostatnia komenda": '{"cmd":"photo"}'})
    try:
        import serial
    except ImportError as e:
        return _missing(e, ["pip install pyserial"])
    if not _dev_exists(port):
        return Result(MISSING, f"Port {port} nie istnieje", hints=HINT_UART)
    try:
        ser = serial.Serial(port, baud, timeout=1)
    except Exception as e:
        return _fail(e, ["Port zajęty przez usługę? sudo systemctl stop stratosteam-air"]
                     + HINT_UART)
    lines: list[str] = []
    try:
        ser.reset_input_buffer()
        # ping — ESP32 ignoruje nieznane komendy, więc to bezpieczne
        ser.write(b'{"cmd":"ping"}\n')
        deadline = time.time() + seconds
        while time.time() < deadline and len(lines) < 5:
            raw = ser.readline().decode("utf-8", errors="replace").strip()
            if raw:
                lines.append(raw)
    except Exception as e:
        return _fail(e, HINT_UART)
    finally:
        ser.close()

    values = {"Port": f"{port} @ {baud} baud", "Odebrane linie": str(len(lines))}
    for i, ln in enumerate(lines[:3]):
        values[f"Linia {i + 1}"] = ln[:80]
    if not lines:
        return Result(WARN, f"Cisza na porcie przez {seconds:.0f} s", values,
                      ["ESP32 wysyła komendy tylko gdy ma je do wysłania — cisza jest normalna",
                       "Żeby sprawdzić kabel: wyślij z ESP32 cokolwiek albo zewrzyj",
                       "   pin 8 (TXD) z pinem 10 (RXD) — wtedy test odbije wysłany ping",
                       "RPi TX (pin 8, GPIO14) → ESP32 GPIO3 (RX)",
                       "RPi RX (pin 10, GPIO15) ← ESP32 GPIO14 (TX)"] + HINT_UART)
    ok_json = sum(1 for ln in lines if _is_json(ln))
    if ok_json == 0:
        return Result(WARN, "Coś przychodzi, ale to nie jest JSON — zła prędkość?", values,
                      [f"Obie strony muszą mieć {baud} baud, 8N1"])
    return Result(OK, f"Łącze działa — odebrano {len(lines)} linii ({ok_json} poprawnych JSON)",
                  values)


def _is_json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except Exception:
        return False


# ── Sygnały GPIO RPi5 ↔ ESP32-S3 ─────────────────────────────────────────────
def test_power_signals() -> Result:
    alive = air("RPI_ALIVE_PIN", 26)
    shtdn = air("ESP32_SHTDN_PIN", 6)
    if SIMULATE:
        return Result(OK, "Symulacja — sygnały sprawne", {
            "RPI_ALIVE": f"GPIO{alive}: przełącza poprawnie",
            "ESP32_SHTDN": f"GPIO{shtdn}: stan niski (ESP32 nie prosi o wyłączenie)"})
    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        return _missing(e, _gpio_hints())
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(alive, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(alive, GPIO.HIGH)
        time.sleep(0.2)
        high = GPIO.input(alive)
        GPIO.output(alive, GPIO.LOW)
        time.sleep(0.2)
        low = GPIO.input(alive)
        GPIO.setup(shtdn, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        shtdn_state = GPIO.input(shtdn)
    except Exception as e:
        return _fail(e, _gpio_hints())
    finally:
        try:
            GPIO.cleanup([alive, shtdn])
        except Exception:
            pass

    values = {
        "RPI_ALIVE": f"GPIO{alive} (pin 37): HIGH={high}, LOW={low}",
        "ESP32_SHTDN": f"GPIO{shtdn} (pin 31): stan {'wysoki' if shtdn_state else 'niski'}",
    }
    if not (high == 1 and low == 0):
        return Result(FAIL, "Pin RPI_ALIVE nie przełącza się", values,
                      ["Pin zajęty przez inny program albo zwarty do masy"])
    if shtdn_state:
        return Result(WARN, "ESP32 trzyma sygnał shutdown w stanie wysokim", values,
                      ["W locie oznacza to prośbę o wyłączenie RPi",
                       "Na stole: odłączony przewód lub ESP32 w resecie"])
    return Result(OK, "Oba sygnały zachowują się poprawnie", values)


# ── Przekaźniki zwalniania linek (akcja niebezpieczna) ───────────────────────
RELAY_PINS = [27, 5]


def test_relays(index: int = -1) -> Result:
    pins = RELAY_PINS if index < 0 else [RELAY_PINS[index]]
    if SIMULATE:
        return Result(INFO, "Symulacja — impuls wysłany na przekaźniki", {
            f"Przekaźnik #{i}": f"GPIO{p}: impuls 300 ms" for i, p in enumerate(pins)})
    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        return _missing(e, _gpio_hints())
    values: dict[str, str] = {}
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for i, pin in enumerate(pins):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(0.3)
            state = GPIO.input(pin)
            GPIO.output(pin, GPIO.LOW)
            values[f"Przekaźnik #{i}"] = (f"GPIO{pin}: impuls 300 ms "
                                          f"({'stan wysoki potwierdzony' if state else 'BRAK stanu wysokiego'})")
            time.sleep(0.3)
    except Exception as e:
        return _fail(e, _gpio_hints())
    finally:
        try:
            GPIO.cleanup(pins)
        except Exception:
            pass
    return Result(INFO, "Impuls wysłany — potwierdź słuchem (kliknięcie przekaźnika)", values,
                  ["Cisza = sprawdź tranzystor (2N2222/BC547) i diodę 1N4007 na cewce",
                   "Cewka 3 V / ~70 mA NIE MOŻE być zasilana wprost z GPIO",
                   "Po teście linka musi być z powrotem zapięta w mechanizmie"])


# ── Nadajnik HF AD9833 (stacja naziemna, akcja niebezpieczna) ────────────────
def test_hf_tx() -> Result:
    """Inicjalizacja AD9833 BEZ kluczowania PTT — brak emisji na antenę."""
    freq = ground("HF_DEFAULT_FREQ_HZ", 7_100_000)
    mclk = ground("AD9833_MCLK_HZ", 25_000_000)
    bus = ground("AD9833_SPI_BUS", 1)
    cs = ground("AD9833_SPI_CS", 1)
    ptt = ground("HF_PTT_PIN", 24)
    if SIMULATE:
        return Result(INFO, "Symulacja — generator ustawiony (bez emisji)", {
            "Port SPI": f"/dev/spidev{bus}.{cs}", "Częstotliwość": f"{freq / 1e6:.3f} MHz",
            "PTT": f"GPIO{ptt}: stan niski (wzmacniacz wyłączony)"})
    try:
        import spidev
    except ImportError as e:
        return _missing(e, ["pip install spidev"] + HINT_SPI)
    if not _dev_exists(f"/dev/spidev{bus}.{cs}"):
        return Result(MISSING, f"Brak /dev/spidev{bus}.{cs} — SPI1 nie jest włączone", hints=[
            "Dodaj do /boot/firmware/config.txt:  dtoverlay=spi1-3cs",
            "Potem reboot i sprawdź: ls /dev/spidev*"] + HINT_SPI)
    spi = None
    try:
        spi = spidev.SpiDev()
        spi.open(bus, cs)
        spi.max_speed_hz = 1_000_000
        spi.mode = 0b10
        word = round(freq * (1 << 28) / mclk) & 0x0FFFFFFF
        lo, hi = word & 0x3FFF, (word >> 14) & 0x3FFF
        for w in (0x2100, 0x4000 | lo, 0x4000 | hi, 0xC000, 0x2000):
            spi.xfer2([(w >> 8) & 0xFF, w & 0xFF])
    except Exception as e:
        return _fail(e, ["AD9833: SCLK → SPI1 CLK (pin 40), MOSI → SPI1 MOSI (pin 38)",
                         "FSYNC/CS → SPI1 CE1 (pin 11), tryb SPI 2 (CPOL=1, CPHA=0)"] + HINT_SPI)
    finally:
        if spi is not None:
            try:
                spi.close()
            except Exception:
                pass

    return Result(INFO, "Generator ustawiony — PTT NIE był kluczowany (brak emisji)", {
        "Port SPI": f"/dev/spidev{bus}.{cs}",
        "Częstotliwość": f"{freq / 1e6:.3f} MHz",
        "Kwarc AD9833": f"{mclk / 1e6:.0f} MHz",
        "PTT": f"GPIO{ptt} (pin 18) — pozostaje w stanie niskim",
    }, ["AD9833 nie ma odczytu rejestrów — sygnał sprawdź oscyloskopem na wyjściu OUT",
        "Nadawanie w paśmie 40 m wymaga uprawnień — kluczuj PTT tylko na sztuczne obciążenie",
        "Przed kluczowaniem MUSI być podłączona antena albo dummy load"])
