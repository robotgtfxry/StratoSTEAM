"""
Przebieg misji na stacji: procedura startu, zegar T+, automatyczne wykrywanie faz lotu.

Fazy: PRZYGOTOWANIE → START (wciśnięty) → WZNOSZENIE → OPADANIE → LĄDOWANIE
Stan leży w pliku, więc restart stacji w trakcie lotu niczego nie gubi.
"""
import json
import logging
import os
import time
from collections import deque

log = logging.getLogger(__name__)

PREP, START, ASCENT, DESCENT, LANDED = "PRZYGOTOWANIE", "START", "WZNOSZENIE", "OPADANIE", "LĄDOWANIE"
IN_FLIGHT = (START, ASCENT, DESCENT)

BARO_MIN_HPA = 320          # niżej barometry są poza zakresem
LAUNCH_CLIMB_M = 60         # tyle nad miejscem startu = lecimy (gdy nikt nie wcisnął START)
LAUNCH_VS = 1.0             # m/s
DROP_M = 150                # tyle poniżej szczytu = opadanie
LAND_STILL_S = 90           # tyle bez zmiany wysokości = wylądował
FLIGHT_REPEAT = 3           # ile razy wysłać balonowi „lot” (łącze bez potwierdzeń)

# Sprawdzenia ręczne: (klucz, opis)
MANUAL = [
    ("antena",  "Anteny LoRa i GPS podłączone"),
    ("sd",      "Karta SD w ESP32-CAM, miejsce na karcie RPi"),
    ("bateria", "Bateria naładowana, przewody 5V pewne"),
    ("spadochron", "Spadochron i linki sprawdzone"),
    ("balon",   "Balon napełniony, udźwig sprawdzony"),
    ("zgoda",   "Zgoda na lot i powiadomienie służb ruchu"),
]


def altitude(flat: dict) -> tuple[float, str] | None:
    """Wysokość i jej źródło: GPS, a bez fixa — barometr w jego zakresie."""
    if flat.get("fix") and flat.get("alt") is not None:
        return float(flat["alt"]), "GPS"
    if flat.get("alt2") and (flat.get("p2") or 0) > BARO_MIN_HPA:
        return float(flat["alt2"]), "baro"
    return None


class Mission:
    def __init__(self, path: str):
        self._path = path
        self.d = {"phase": PREP, "t0": None, "alt0": None, "max_alt": None,
                  "events": [], "manual": {}}
        self._alts: deque = deque(maxlen=8)     # (czas, wysokość)
        self._src = None
        self._ground: deque = deque(maxlen=60)
        self._still_since: float | None = None
        self._flight_cmds: list[bool] = []
        self.vs: float | None = None
        self.alt: float | None = None
        try:
            with open(path, encoding="utf-8") as f:
                self.d.update(json.load(f))
        except (OSError, ValueError):
            pass

    # ── polecenia z okna ──────────────────────────────────────────────────────

    def command(self, c: dict, now: float) -> None:
        a = c.get("a")
        if a == "manual" and c.get("k") in dict(MANUAL):
            self.d["manual"][c["k"]] = bool(c.get("v"))
            self._save()
        elif a == "start" and self.d["phase"] == PREP:
            self.d.update(t0=now, max_alt=None)
            if self._ground:
                self.d["alt0"] = sorted(self._ground)[len(self._ground) // 2]
            skipped = [str(x)[:60] for x in c.get("skipped", [])][:20]
            self._phase(START, now, "START wciśnięty" + (f" mimo: {', '.join(skipped)}" if skipped else ""))
            self._flight_cmds = [True] * FLIGHT_REPEAT
        elif a == "reset":
            self.d.update(phase=PREP, t0=None, alt0=None, max_alt=None, manual={})
            self._ground.clear()
            self._still_since = None
            self._event(now, "Nowa procedura startu")
            self._flight_cmds = [False] * FLIGHT_REPEAT

    def pop_flight(self) -> bool | None:
        """Czy wysłać teraz balonowi komendę „lot” (True/False)."""
        return self._flight_cmds.pop(0) if self._flight_cmds else None

    # ── telemetria ────────────────────────────────────────────────────────────

    def update(self, flat: dict, now: float) -> None:
        got = altitude(flat)
        if got is None:
            self.vs = self.alt = None
            return
        alt, src = got
        if src != self._src:            # GPS i barometr różnią się o setki metrów
            self._alts.clear()
            self._ground.clear()
            self._still_since = None
            self._src = src
        self.alt = alt
        self._alts.append((now, alt))
        t0, a0 = self._alts[0]
        self.vs = (alt - a0) / (now - t0) if now - t0 >= 15 else None

        phase = self.d["phase"]
        if phase == PREP:
            base = sorted(self._ground)[len(self._ground) // 2] if len(self._ground) >= 6 else None
            if base is not None and self.vs is not None and self.vs > LAUNCH_VS \
                    and alt - base > LAUNCH_CLIMB_M:
                self.d.update(t0=now, alt0=base, max_alt=alt)
                self._phase(ASCENT, now, "Start wykryty automatycznie")
                self._flight_cmds = [True] * FLIGHT_REPEAT
            elif base is None or abs(alt - base) < LAUNCH_CLIMB_M / 2:
                self._ground.append(alt)
            return
        if phase == LANDED:
            return

        self.d["max_alt"] = max(alt, self.d["max_alt"] if self.d["max_alt"] is not None else alt)
        if phase == START:
            if self.d["alt0"] is None:
                self.d["alt0"] = alt
            if self.vs is not None and self.vs > LAUNCH_VS and alt - self.d["alt0"] > 20:
                self._phase(ASCENT, now, "Balon się wznosi")
        elif phase == ASCENT:
            if self.vs is not None and self.vs < -1 and self.d["max_alt"] - alt > DROP_M:
                self._phase(DESCENT, now, f"Opadanie, szczyt {self.d['max_alt']:.0f} m")
        elif phase == DESCENT:
            still = self.vs is not None and abs(self.vs) < 0.5
            self._still_since = (self._still_since or now) if still else None
            if self._still_since and now - self._still_since >= LAND_STILL_S:
                self._phase(LANDED, now, "Lądowanie")

    def _phase(self, phase: str, now: float, text: str) -> None:
        self.d["phase"] = phase
        self._event(now, text)

    def _event(self, now: float, text: str) -> None:
        log.info("MISJA: %s [%s]", text, self.d["phase"])
        self.d["events"] = (self.d["events"] + [[now, text]])[-30:]
        self._save()

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.d, f, ensure_ascii=False)
            os.replace(self._path + ".tmp", self._path)
        except OSError as e:
            log.warning("Misja: nie mogę zapisać stanu (%s)", e)

    def state(self) -> dict:
        return {**self.d, "vs": self.vs, "alt": self.alt, "src": self._src}


def preflight(st: dict, now: float) -> list[tuple[str, bool | None, str]]:
    """Automatyczne sprawdzenia: (opis, wynik, wartość). None = brak danych."""
    p = st.get("last") or {}
    age = now - st["last_rx"] if st.get("last_rx") else None
    fresh = age is not None and age < 15
    total = st.get("packets", 0) + st.get("lost", 0)
    loss = st.get("lost", 0) / total * 100 if total else None
    ec = p.get("ec") if isinstance(p.get("ec"), list) and len(p.get("ec")) >= 4 else None
    rpi = fresh and "temp" in p
    photo = st.get("photo")
    reset_at = st.get("lora_reset_at")
    vbe = p.get("vbe")

    def val(v, unit, d=0):
        return "—" if v is None else f"{v:.{d}f} {unit}"

    return [
        ("Stacja odbiera pakiety", fresh, "—" if age is None else f"{age:.0f} s temu"),
        ("Straty pakietów < 10%", None if loss is None else loss < 10, val(loss, "%", 1)),
        ("Sygnał LoRa (SNR > 0)", None if st.get("snr") is None else st["snr"] > 0, val(st.get("snr"), "dB", 1)),
        ("Moduł LoRa stacji stabilny (10 min)", not (reset_at and now - reset_at < 600),
         f"resety: {st.get('lora_resets', 0)}"),
        ("GPS: fix i min. 6 satelitów", bool(p.get("fix")) and (p.get("sat") or 0) >= 6 if p else None,
         f"{p.get('sat', 0)} sat." if p else "—"),
        ("RPi balonu przysyła czujniki", rpi if p else None, val(p.get("temp"), "°C", 1)),
        ("Napięcie S3 powyżej 4,75 V", None if vbe is None else vbe > 4.75, val(vbe, "V", 2)),
        ("Ciśnienie wiarygodne", None if p.get("pres") is None else 850 < p["pres"] < 1100,
         val(p.get("pres"), "hPa")),
        ("ESP32-CAM nagrywa", None if ec is None else bool(ec[0] and ec[1]),
         "—" if ec is None else ("nagrywa" if ec[1] else "NIE nagrywa")),
        ("Dysk RPi: min. 5 GB wolne", None if p.get("dskf") is None else p["dskf"] >= 5,
         val(p.get("dskf"), "GB", 1)),
        ("Zdjęcie przez LoRa (30 min)", bool(photo and photo.get("done") and now - photo["ts"] < 1800),
         "jest" if photo and photo.get("done") else "brak"),
    ]
