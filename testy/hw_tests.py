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

from repo import air, is_pi5, load_repo_module

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


# ── I2C: wspólne ─────────────────────────────────────────────────────────────
MPU6050_ADDR = air("MPU6050_ADDR", 0x68)
BMP180_ADDR = air("BMP180_ADDR", 0x77)
INA226_ADDR = air("INA226_ADDR", 0x44)
INA226_SHUNT_OHMS = air("INA226_SHUNT_OHMS", 0.1)
QMC5883L_ADDR = 0x0D
HMC5883L_ADDR = 0x1E

HINT_GY87 = [
    "GY-87 to jedna płytka: MPU-6050 (0x68) + BMP180 (0x77) + magnetometr",
    "VCC_IN modułu → 3.3 V (pin 1) albo 5 V — płytka ma własny stabilizator",
]


def _i2c_bus():
    """Otwiera I2C-1. Rzuca ImportError (brak smbus2) albo OSError (brak magistrali)."""
    import smbus2
    return smbus2.SMBus(1)


def _i2c_open() -> tuple[object | None, Result | None]:
    """(bus, None) albo (None, gotowy Result z błędem) — do użycia na początku testu."""
    if not _dev_exists("/dev/i2c-1"):
        return None, Result(MISSING, "Brak /dev/i2c-1 — magistrala I2C jest wyłączona",
                            hints=HINT_I2C)
    try:
        return _i2c_bus(), None
    except ImportError as e:
        return None, _missing(e, ["pip install smbus2", "lub: sudo apt install python3-smbus2"])
    except OSError as e:
        return None, _fail(e, HINT_I2C)


def _u16be(hi: int, lo: int) -> int:
    return (hi << 8) | lo


def _s16be(hi: int, lo: int) -> int:
    v = (hi << 8) | lo
    return v - 0x10000 if v & 0x8000 else v


def _s16le(lo: int, hi: int) -> int:
    return _s16be(hi, lo)


def _reg(bus, addr: int, reg: int) -> int | None:
    """Jeden bajt rejestru albo None, gdy układ nie odpowiada."""
    try:
        return bus.read_byte_data(addr, reg)
    except OSError:
        return None


def _gy87_bypass(bus) -> None:
    """Budzi MPU-6050 i włącza bypass I2C — magnetometr GY-87 staje się widoczny na magistrali."""
    bus.write_byte_data(MPU6050_ADDR, 0x6B, 0x00)   # PWR_MGMT_1: wybudź
    time.sleep(0.05)
    bus.write_byte_data(MPU6050_ADDR, 0x6A, 0x00)   # USER_CTRL: wyłącz tryb I2C master
    bus.write_byte_data(MPU6050_ADDR, 0x37, 0x02)   # INT_PIN_CFG: I2C_BYPASS_EN
    time.sleep(0.01)


# ── I2C: skan magistrali ─────────────────────────────────────────────────────
I2C_KNOWN = {
    0x0D: "QMC5883L (magnetometr GY-87)",
    0x1E: "HMC5883L (magnetometr GY-87)",
    0x40: "INA226 (prąd/napięcie baterii)",
    0x41: "INA226 — adres alternatywny",
    0x44: "INA226 — adres alternatywny",
    0x45: "INA226 — adres alternatywny",
    0x68: "MPU-6050 (akcelerometr/żyroskop GY-87)",
    0x69: "MPU-6050 — adres alternatywny (AD0 = 1)",
    0x76: "BME280 (temperatura/wilgotność/ciśnienie)",
    0x77: "BMP180 (ciśnienie GY-87)",
}

# rejestr ID układów Boscha (0xD0) i MPU (0x75) — żeby skan mówił, co NAPRAWDĘ siedzi pod adresem
_BOSCH_ID = {0x55: "BMP180", 0x58: "BMP280", 0x60: "BME280", 0x61: "BME680"}
_MPU_ID = {0x68: "MPU-6050", 0x70: "MPU-6500", 0x71: "MPU-9250", 0x73: "MPU-9255",
           0x72: "MPU-6050 (klon)", 0x98: "MPU-6050 (klon)"}


def _identify(bus, addr: int) -> str:
    if 0x40 <= addr <= 0x4F and _is_ina226(bus, addr):
        return "INA226 (manufacturer ID 0x5449)"
    if addr in (0x76, 0x77):
        cid = _reg(bus, addr, 0xD0)
        if cid in _BOSCH_ID:
            return f"{_BOSCH_ID[cid]} (chip ID 0x{cid:02X})"
    if addr in (0x68, 0x69):
        who = _reg(bus, addr, 0x75)
        if who in _MPU_ID:
            return f"{_MPU_ID[who]} (WHO_AM_I 0x{who:02X})"
    return I2C_KNOWN.get(addr, "nieznany układ")


def test_i2c_scan() -> Result:
    """Odpowiednik i2cdetect -y 1 — pokazuje wszystkie układy na magistrali."""
    if SIMULATE:
        found = [0x0D, 0x44, 0x68, 0x76, 0x77]
        return Result(OK, f"Symulacja: znaleziono {len(found)} układów na I2C-1",
                      {f"0x{a:02X}": I2C_KNOWN.get(a, "nieznany") for a in found})

    bus, err = _i2c_open()
    if err:
        return err
    found: list[int] = []
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
        values = {f"0x{a:02X}": _identify(bus, a) for a in found}
    finally:
        bus.close()

    if not found:
        return Result(FAIL, "Magistrala I2C pusta — żaden układ nie odpowiada",
                      hints=HINT_I2C + ["Sprawdź zasilanie modułów (3.3 V, nie 5 V!)"])
    expected = {0x76: "BME280", 0x68: "MPU-6050", 0x77: "BMP180"}
    brak = [n for a, n in expected.items() if a not in found]
    # INA226 może siedzieć pod dowolnym adresem 0x40…0x4F (zworki A0/A1)
    if not any(v.startswith("INA226 (") for v in values.values()):
        brak.append("INA226")
    hints = []
    if 0x68 in found and not ({QMC5883L_ADDR, HMC5883L_ADDR} & set(found)):
        hints.append("Magnetometr GY-87 jest schowany za MPU-6050 — pokaże się "
                     "po teście magnetometru (włącza bypass I2C)")
    if brak:
        return Result(WARN, f"Znaleziono {len(found)} adresów, brakuje: {', '.join(brak)}",
                      values,
                      ["Każdy brakujący układ sprawdź osobno na liście po lewej"] + hints + HINT_I2C)
    return Result(OK, f"Wszystkie układy I2C odpowiadają ({len(found)} adresów)", values, hints)


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
        return _missing(e, ["pip install smbus2 pimoroni-bme280",
                            "lub: sudo apt install python3-smbus2"])
    try:
        sensor = mod.Bme280Sensor(addr, 1)
        sensor.read()          # pierwszy odczyt tylko budzi przetwornik
        time.sleep(0.2)
        d = sensor.read()
    except Exception as e:
        return _fail(e, [f"Czujnik nie odpowiada pod adresem 0x{addr:02X}",
                         "Część modułów ma adres 0x77 (zworka SDO/ADDR) — "
                         "wtedy koliduje z BMP180 na GY-87"] + HINT_I2C)

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


# ── GY-87: MPU-6050 (akcelerometr + żyroskop) ────────────────────────────────
def test_mpu6050() -> Result:
    addr = MPU6050_ADDR
    if SIMULATE:
        return Result(OK, "Symulacja — MPU-6050 odpowiada", {
            "WHO_AM_I": "0x68 (MPU-6050)",
            "Akcelerometr": f"x={_jitter(0.02, 0.02)} y={_jitter(-0.01, 0.02)} "
                            f"z={_jitter(1.0, 0.02)} g",
            "Wektor przyspieszenia": "1.00 g (czujnik leży nieruchomo)",
            "Roll / Pitch": f"{_jitter(0.8, 0.5, 1)}° / {_jitter(-1.1, 0.5, 1)}°",
            "Żyroskop": f"x={_jitter(0.4, 0.3)} y={_jitter(-0.6, 0.3)} z={_jitter(0.2, 0.3)} °/s",
            "Temperatura układu": f"{_jitter(27.5, 0.3, 1)} °C"})
    bus, err = _i2c_open()
    if err:
        return err
    try:
        who = bus.read_byte_data(addr, 0x75)
        bus.write_byte_data(addr, 0x6B, 0x01)     # wybudź, zegar z PLL żyroskopu X
        time.sleep(0.1)
        bus.write_byte_data(addr, 0x1A, 0x03)     # filtr DLPF ~44 Hz
        bus.write_byte_data(addr, 0x1B, 0x00)     # żyroskop ±250 °/s → 131 LSB/(°/s)
        bus.write_byte_data(addr, 0x1C, 0x00)     # akcelerometr ±2 g → 16384 LSB/g
        time.sleep(0.05)
        n = 20
        acc = [0.0, 0.0, 0.0]
        gyr = [0.0, 0.0, 0.0]
        temp = 0.0
        for _ in range(n):
            b = bus.read_i2c_block_data(addr, 0x3B, 14)
            raw = [_s16be(b[i], b[i + 1]) for i in range(0, 14, 2)]
            for k in range(3):
                acc[k] += raw[k] / 16384.0 / n
                gyr[k] += raw[4 + k] / 131.0 / n
            temp += (raw[3] / 340.0 + 36.53) / n
            time.sleep(0.01)
        _gy87_bypass(bus)                          # przy okazji odsłoń magnetometr
    except OSError as e:
        return _fail(e, [f"MPU-6050 nie odpowiada pod adresem 0x{addr:02X}",
                         "Pin AD0 na masę → 0x68, na 3.3 V → 0x69"] + HINT_GY87 + HINT_I2C)
    finally:
        bus.close()

    g = math.sqrt(sum(a * a for a in acc))
    roll = math.degrees(math.atan2(acc[1], acc[2]))
    pitch = math.degrees(math.atan2(-acc[0], math.hypot(acc[1], acc[2])))
    values = {
        "WHO_AM_I": f"0x{who:02X} ({_MPU_ID.get(who, 'nieznany układ')})",
        "Akcelerometr": f"x={acc[0]:.2f} y={acc[1]:.2f} z={acc[2]:.2f} g",
        "Wektor przyspieszenia": f"{g:.2f} g (powinno być ~1.00)",
        "Roll / Pitch": f"{roll:.1f}° / {pitch:.1f}°",
        "Żyroskop": f"x={gyr[0]:.1f} y={gyr[1]:.1f} z={gyr[2]:.1f} °/s",
        "Temperatura układu": f"{temp:.1f} °C",
    }
    if all(a == 0 for a in acc) and all(w == 0 for w in gyr):
        return Result(FAIL, "MPU-6050 odpowiada, ale zwraca same zera", values,
                      ["Układ w uśpieniu albo uszkodzony — odłącz zasilanie na kilka sekund"])
    if not 0.8 <= g <= 1.2:
        return Result(WARN, "Akcelerometr odpowiada, ale przyspieszenie ≠ 1 g", values,
                      ["Połóż moduł nieruchomo na stole i powtórz test"])
    if max(abs(w) for w in gyr) > 10:
        return Result(WARN, "Żyroskop pokazuje obrót, choć moduł powinien leżeć", values,
                      ["Nie ruszaj modułu podczas testu",
                       "Stałe przesunięcie kilku °/s to normalny offset — kalibruje się "
                       "w oprogramowaniu"])
    if who not in (0x68, 0x72, 0x98):
        return Result(WARN, "Odczyt poprawny, ale to nie jest MPU-6050", values,
                      ["Na płytce siedzi inny układ z rodziny MPU — rejestry danych są te same"])
    return Result(OK, "Odczyt poprawny, czujnik widzi 1 g", values)


# ── GY-87: magnetometr (QMC5883L albo HMC5883L) ──────────────────────────────
def _read_qmc5883l(bus) -> tuple[float, float, float]:
    """Pole w µT. Zakres 8 G → 3000 LSB/G."""
    bus.write_byte_data(QMC5883L_ADDR, 0x0A, 0x80)    # soft reset
    time.sleep(0.01)
    bus.write_byte_data(QMC5883L_ADDR, 0x0B, 0x01)    # okres SET/RESET (wg noty)
    bus.write_byte_data(QMC5883L_ADDR, 0x09, 0x1D)    # OSR 512, 8 G, 200 Hz, ciągły
    deadline = time.time() + 0.5
    while time.time() < deadline and not (bus.read_byte_data(QMC5883L_ADDR, 0x06) & 0x01):
        time.sleep(0.01)
    b = bus.read_i2c_block_data(QMC5883L_ADDR, 0x00, 6)
    x, y, z = (_s16le(b[i], b[i + 1]) / 3000.0 * 100.0 for i in (0, 2, 4))
    return x, y, z


def _read_hmc5883l(bus) -> tuple[float, float, float]:
    """Pole w µT. Wzmocnienie ±1.3 G → 1090 LSB/G. Kolejność rejestrów: X, Z, Y."""
    bus.write_byte_data(HMC5883L_ADDR, 0x00, 0x70)    # 8 uśrednień, 15 Hz
    bus.write_byte_data(HMC5883L_ADDR, 0x01, 0x20)    # ±1.3 G
    bus.write_byte_data(HMC5883L_ADDR, 0x02, 0x00)    # pomiar ciągły
    time.sleep(0.1)
    b = bus.read_i2c_block_data(HMC5883L_ADDR, 0x03, 6)
    x, z, y = (_s16be(b[i], b[i + 1]) / 1090.0 * 100.0 for i in (0, 2, 4))
    return x, y, z


def test_magnetometer() -> Result:
    if SIMULATE:
        return Result(OK, "Symulacja — magnetometr odpowiada", {
            "Układ": "QMC5883L (0x0D)",
            "Pole": f"x={_jitter(18.0, 1.0, 1)} y={_jitter(-4.0, 1.0, 1)} "
                    f"z={_jitter(-42.0, 1.0, 1)} µT",
            "Natężenie": f"{_jitter(46.0, 1.0, 1)} µT (Ziemia ok. 50 µT)",
            "Kierunek (kompas)": f"{_jitter(347.0, 2.0, 0):.0f}°"})
    bus, err = _i2c_open()
    if err:
        return err
    chip = None
    try:
        try:
            _gy87_bypass(bus)
        except OSError:
            pass    # brak MPU-6050 — magnetometr może być osobnym modułem
        if _reg(bus, QMC5883L_ADDR, 0x0D) == 0xFF:
            chip, (x, y, z) = f"QMC5883L (0x{QMC5883L_ADDR:02X})", _read_qmc5883l(bus)
        elif _reg(bus, HMC5883L_ADDR, 0x0A) == ord("H"):     # ID: "H43"
            chip, (x, y, z) = f"HMC5883L (0x{HMC5883L_ADDR:02X})", _read_hmc5883l(bus)
    except OSError as e:
        return _fail(e, HINT_GY87 + HINT_I2C)
    finally:
        bus.close()

    if chip is None:
        return Result(FAIL, "Nie znaleziono magnetometru (ani QMC5883L 0x0D, ani HMC5883L 0x1E)",
                      hints=["Na GY-87 magnetometr wisi za MPU-6050 — najpierw musi działać "
                             "test MPU-6050",
                             "Po teście sprawdź: i2cdetect -y 1 → powinien być 0x0D albo 0x1E"]
                      + HINT_GY87 + HINT_I2C)

    total = math.sqrt(x * x + y * y + z * z)
    heading = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    values = {
        "Układ": chip,
        "Pole": f"x={x:.1f} y={y:.1f} z={z:.1f} µT",
        "Natężenie": f"{total:.1f} µT (Ziemia ok. 50 µT, bez kalibracji ± kilkadziesiąt)",
        "Kierunek (kompas)": f"{heading:.0f}° (bez kalibracji, moduł poziomo)",
    }
    if total == 0:
        return Result(FAIL, "Magnetometr odpowiada, ale zwraca same zera", values,
                      ["Odłącz zasilanie modułu na kilka sekund i powtórz"])
    if not 10 <= total <= 100:
        return Result(WARN, "Natężenie pola nietypowe — magnes lub metal w pobliżu?", values,
                      ["Odsuń moduł od głośników, silników, śrubokrętów i przewodów z prądem",
                       "Przed lotem zrób kalibrację (obracanie modułem we wszystkich osiach)"])
    return Result(OK, "Odczyt poprawny", values,
                  ["Kierunek jest orientacyjny — kompas wymaga kalibracji hard/soft-iron"])


# ── GY-87: BMP180 (ciśnienie + temperatura) ──────────────────────────────────
def _tdiv(a: int, b: int) -> int:
    """Dzielenie całkowite z obcięciem do zera — jak w C (algorytm z noty BMP180)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _bmp180_read(bus, addr: int, oss: int = 3) -> tuple[float, float]:
    """(temperatura °C, ciśnienie hPa) — algorytm z noty katalogowej Boscha."""
    c = bus.read_i2c_block_data(addr, 0xAA, 22)
    w = [_u16be(c[i], c[i + 1]) for i in range(0, 22, 2)]
    s = [v - 0x10000 if v & 0x8000 else v for v in w]
    ac1, ac2, ac3 = s[0], s[1], s[2]
    ac4, ac5, ac6 = w[3], w[4], w[5]
    b1, b2, _mb, mc, md = s[6], s[7], s[8], s[9], s[10]
    if 0 in (ac5, ac6, md) or 0xFFFF in w:
        raise OSError("nieprawidłowe dane kalibracyjne BMP180 (EEPROM)")

    bus.write_byte_data(addr, 0xF4, 0x2E)
    time.sleep(0.005)
    b = bus.read_i2c_block_data(addr, 0xF6, 2)
    ut = _u16be(b[0], b[1])
    bus.write_byte_data(addr, 0xF4, 0x34 + (oss << 6))
    time.sleep(0.026)
    b = bus.read_i2c_block_data(addr, 0xF6, 3)
    up = ((b[0] << 16) | (b[1] << 8) | b[2]) >> (8 - oss)

    x1 = ((ut - ac6) * ac5) >> 15
    x2 = _tdiv(mc << 11, x1 + md)
    b5 = x1 + x2
    temp_c = ((b5 + 8) >> 4) / 10.0

    b6 = b5 - 4000
    x1 = (b2 * ((b6 * b6) >> 12)) >> 11
    x2 = (ac2 * b6) >> 11
    x3 = x1 + x2
    b3 = _tdiv(((ac1 * 4 + x3) << oss) + 2, 4)
    x1 = (ac3 * b6) >> 13
    x2 = (b1 * ((b6 * b6) >> 12)) >> 16
    x3 = (x1 + x2 + 2) >> 2
    b4 = (ac4 * (x3 + 32768)) >> 15
    b7 = (up - b3) * (50000 >> oss)
    p = _tdiv(b7 * 2, b4) if b7 < 0x80000000 else _tdiv(b7, b4) * 2
    x1 = ((p >> 8) * (p >> 8) * 3038) >> 16
    x2 = (-7357 * p) >> 16
    p += (x1 + x2 + 3791) >> 4
    return temp_c, p / 100.0


def test_bmp180() -> Result:
    addr = BMP180_ADDR
    if SIMULATE:
        p = _jitter(1002.9, 0.3)
        return Result(OK, "Symulacja — BMP180 odpowiada", {
            "Chip ID": "0x55 (BMP180)", "Ciśnienie": f"{p} hPa",
            "Temperatura": f"{_jitter(22.1, 0.2)} °C", "Wysokość": f"{_altitude_m(p):.1f} m"})
    bus, err = _i2c_open()
    if err:
        return err
    try:
        cid = bus.read_byte_data(addr, 0xD0)
        if cid != 0x55:
            name = _BOSCH_ID.get(cid, "nieznany układ")
            return Result(FAIL, f"Pod 0x{addr:02X} nie ma BMP180 (chip ID 0x{cid:02X} = {name})",
                          {"Chip ID": f"0x{cid:02X}"},
                          ["BME280 ze zworką SDO na 3.3 V też ma adres 0x77 — kolizja z GY-87",
                           "Przełącz BME280 na 0x76"])
        temp_c, p = _bmp180_read(bus, addr)
    except OSError as e:
        return _fail(e, [f"BMP180 nie odpowiada pod adresem 0x{addr:02X}"] + HINT_GY87 + HINT_I2C)
    finally:
        bus.close()

    values = {
        "Chip ID": "0x55 (BMP180)",
        "Ciśnienie": f"{p:.2f} hPa",
        "Temperatura": f"{temp_c:.1f} °C",
        "Wysokość": f"{_altitude_m(p):.1f} m",
    }
    if not (300 <= p <= 1100) or not (-40 <= temp_c <= 85):
        return Result(WARN, "Czujnik odpowiada, ale wartości są poza zakresem", values,
                      ["BMP180 mierzy 300–1100 hPa — powyżej ~9 km wysokości kończy mu się zakres",
                       "Na stole wynik poza zakresem = uszkodzony moduł lub zakłócenia I2C"])
    return Result(OK, "Odczyt poprawny", values,
                  ["BMP180 mierzy tylko do 300 hPa (~9 km) — w stratosferze wysokość "
                   "bierz z GPS"])


# ── INA226 (bateria) ─────────────────────────────────────────────────────────
def _ina_read(bus, addr: int, reg: int) -> int:
    b = bus.read_i2c_block_data(addr, reg, 2)
    return _u16be(b[0], b[1])


def _is_ina226(bus, addr: int) -> bool:
    try:
        return _ina_read(bus, addr, 0xFE) == 0x5449
    except OSError:
        return False


def _find_ina226(bus) -> int | None:
    """Najpierw adres z konfiguracji, potem cały zakres zworek A0/A1 (0x40…0x4F)."""
    for addr in [INA226_ADDR] + [a for a in range(0x40, 0x50) if a != INA226_ADDR]:
        if _is_ina226(bus, addr):
            return addr
    return None


def test_ina226() -> Result:
    addr = INA226_ADDR
    shunt = INA226_SHUNT_OHMS
    if SIMULATE:
        v, i = _jitter(7.82, 0.05, 3), _jitter(430.0, 25.0)
        return Result(OK, "Symulacja — INA226 odpowiada", {
            "Napięcie": f"{v} V", "Prąd": f"{i} mA", "Moc": f"{round(v * i, 1)} mW",
            "Bocznik": f"{shunt} Ω"})
    bus, err = _i2c_open()
    if err:
        return err
    try:
        found = _find_ina226(bus)
        if found is None:
            return Result(FAIL, "Nie znaleziono INA226 pod żadnym adresem 0x40…0x4F",
                          hints=["Sprawdź skan I2C — czy coś odpowiada w zakresie 0x40…0x4F?",
                                 "INA219 nie ma rejestru ID (0xFE) — sprawdź, czy to na pewno INA226"]
                                + HINT_I2C)
        addr = found
        die = _ina_read(bus, addr, 0xFF)
        # uśrednianie 16, czas konwersji 1.1 ms, pomiar ciągły bocznika i szyny
        bus.write_i2c_block_data(addr, 0x00, [0x45, 0x27])
        time.sleep(0.1)
        raw_shunt = _ina_read(bus, addr, 0x01)
        raw_bus = _ina_read(bus, addr, 0x02)
    except OSError as e:
        return _fail(e, [f"Brak odpowiedzi pod adresem 0x{addr:02X}",
                         "Adres zależy od zworek A0/A1 (0x40…0x4F) — zobacz skan I2C"] + HINT_I2C)
    finally:
        bus.close()

    v_shunt_mv = (raw_shunt - 0x10000 if raw_shunt & 0x8000 else raw_shunt) * 0.0025
    voltage = raw_bus * 0.00125
    current_ma = v_shunt_mv / shunt
    values = {
        "Napięcie": f"{voltage:.3f} V",
        "Prąd": f"{current_ma:.1f} mA",
        "Moc": f"{voltage * current_ma:.0f} mW",
        "Napięcie na boczniku": f"{v_shunt_mv:.3f} mV",
        "Bocznik": f"{shunt} Ω (max {81.92 / shunt:.0f} mA)",
        "Die ID": f"0x{die:04X}",
        "Adres": f"0x{addr:02X}",
    }
    hints = []
    if addr != INA226_ADDR:
        hints.append(f"INA226 znaleziony pod 0x{addr:02X}, a w konfiguracji jest 0x{INA226_ADDR:02X} — "
                     f"ustaw INA226_ADDR = 0x{addr:02X} w rpi-air/config.py")
    if voltage < 1.0:
        return Result(WARN, "Układ odpowiada, ale nie widzi napięcia na wejściu", values,
                      ["Bateria idzie przez zaciski VIN+ / VIN− (bocznik), nie przez VCC",
                       "VCC modułu (3.3 V) zasila tylko elektronikę pomiarową"] + hints)
    if abs(v_shunt_mv) >= 81.9:
        return Result(WARN, "Przekroczony zakres bocznika — prąd za duży", values,
                      [f"Przy {shunt} Ω INA226 mierzy najwyżej {81.92 / shunt:.0f} mA",
                       "Wymień bocznik na mniejszy (np. 0.01 Ω) i zmień INA226_SHUNT_OHMS"] + hints)
    if abs(current_ma) < 1.0:
        return Result(WARN, "Napięcie OK, ale prąd ≈ 0 — brak obciążenia?", values,
                      ["Sprawdź czy odbiornik jest podłączony za bocznikiem (VIN−)"] + hints)
    if current_ma < 0:
        return Result(WARN, "Prąd ujemny — zamienione VIN+ z VIN−", values,
                      ["Bateria → VIN+, VIN− → odbiornik"] + hints)
    return Result(OK, "Odczyt poprawny", values, hints)


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
                         "   sudo systemctl stop rpi-air"])
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
    if pin is None:
        return Result(INFO, "Kamera zasilana na stałe z USB — nie ma czego przełączać", {},
                      ["ESPCAM_PWR_PIN = None w rpi-air/config.py"])
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


# ── ESP32-CAM: status po USB ─────────────────────────────────────────────────
# Ten sam sterownik, który leci na balonie: wyszukuje CH340 i otwiera port bez resetu kamery.
HINT_ESPCAM_USB = [
    "Kabel USB musi mieć linie danych (nie tylko ładowanie)",
    "Sprawdź, czy system widzi nakładkę: lsusb | grep -i 1a86   oraz: ls /dev/ttyUSB*",
    "Brak uprawnień? sudo usermod -aG dialout $USER i wyloguj się",
    "Port zajęty przez usługę? sudo systemctl stop rpi-air",
]


def _espcam_usb(mod, port: str, baud: int, seconds: float) -> tuple[dict | None, int, str]:
    """Nasłuch po USB. Zwraca (status, liczba odebranych linii, użyty port)."""
    status, lines = None, 0
    ser = mod.open_port(port, baud, timeout=0.5)
    try:
        deadline = time.time() + seconds
        while time.time() < deadline and not status:
            raw = ser.readline()
            if raw.strip():
                lines += 1
                status = mod.EspCamMonitor.parse_line(raw)
        return status, lines, ser.port
    finally:
        ser.close()


def test_espcam_status(seconds: float = 15.0) -> Result:
    baud = air("ESPCAM_STATUS_BAUD", 115200)
    port = air("ESPCAM_UART_PORT", "auto")
    if SIMULATE:
        return Result(OK, "Symulacja — kamera raportuje status", {
            "Odczyt": f"USB {port} @ {baud} baud",
            "Stan": "OK, nagrywa",
            "Klatki": f"{random.randint(900, 4000)}",
            "Wolne na karcie": f"{random.randint(3000, 12000)} MB"})

    try:
        mod = load_repo_module("air_espcam_monitor", "rpi-air/hardware/espcam_monitor.py")
    except (ImportError, FileNotFoundError) as e:
        return _missing(e, ["pip install pyserial"])
    if not mod._SERIAL:
        return Result(MISSING, "Brak biblioteki pyserial", hints=["pip install pyserial"])
    try:
        status, lines, used = _espcam_usb(mod, port, baud, seconds)
    except Exception as e:
        return _fail(e, HINT_ESPCAM_USB)

    source = f"{used} @ {baud} baud"
    if not status:
        return Result(FAIL, "Kamera nie przysłała statusu", {
            "Odczyt": source, "Odebrane linie": str(lines)},
            ["Czy na kamerze jest wgrany firmware? cd espcam && pio run -t upload",
             f"Prędkość musi być {baud} baud (tak nadaje espcam/src/main.cpp)",
             "Kamera nadaje linie z prefiksem $S co ~5 s — reszta jest ignorowana"]
            + (["Linie przychodzą, ale bez $S — zła prędkość albo kamera w trybie boot"]
               if lines else HINT_ESPCAM_USB))

    free_mb = status["free_mb"]
    values = {
        "Odczyt": source,
        "Stan": "OK" if status["ok"] else "kamera zgłasza błąd",
        "Nagrywanie": "tak" if status["recording"] else "nie",
        "Klatki": f"{status['frames']}",
        "Wolne na karcie": f"{free_mb} MB",
    }
    if not status["ok"]:
        return Result(WARN, "Kamera odpowiada, ale zgłasza błąd sensora", values,
                      ["Sprawdź taśmę kamery. Dioda: 2× mignięcie = brak SD, 3× = błąd kamery"])
    if not status["recording"]:
        return Result(WARN, "Kamera odpowiada, ale nie nagrywa", values,
                      ["Sprawdź kartę SD w ESP32-CAM (FAT32, do 32 GB)"])
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
        return _fail(e, ["Port zajęty przez usługę? sudo systemctl stop rpi-air"]
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
