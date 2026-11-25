#!/usr/bin/env python3
"""
StratoSTEAM — okno odbioru na stacji naziemnej (tkinter).

Pokazuje dane odbierane przez usługę rpi-ground (local_feed.py). Samo nie dotyka radia,
więc można je otwierać i zamykać w trakcie lotu.

  python3 gui_odbior.py          normalnie
  python3 gui_odbior.py --demo   udawane dane, bez stacji
"""
import json
import math
import sys
import time
import tkinter as tk

from local_feed import STATE_PATH

REFRESH_MS = 500
SERVICE_TIMEOUT_S = 10      # brak znaku życia usługi
FRESH_S, STALE_S = 15, 60   # wiek ostatniego pakietu: zielony / żółty / czerwony

BG, CARD, LINE = "#0d1117", "#161b22", "#30363d"
FG, DIM = "#e6edf3", "#8b949e"
OK, WARN, BAD, BLUE = "#3fb950", "#d29922", "#f85149", "#58a6ff"
FONT = "DejaVu Sans"


def fmt(value, unit: str = "", digits: int = 1) -> str:
    """Brak danych to „—”, nigdy zero."""
    if value is None or isinstance(value, str):
        return "—"
    return f"{value:.{digits}f}{(' ' + unit) if unit else ''}"


def ago(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min {s % 60:02d} s"
    return f"{s // 3600} h {s % 3600 // 60:02d} min"


def read_state() -> dict | None:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def demo_state(t0: float = time.time()) -> dict:
    now = time.time()
    age = now - t0 + 900
    hist = [[now - 5 * (180 - i), 120 + 5 * (age - 5 * (180 - i)) + 8 * math.sin(i / 3),
             -88 - i / 9 + 3 * math.sin(i / 2)] for i in range(180)]
    return {
        "started": now - 4000, "alive": now, "packets": 212, "bad": 1, "lost": 6, "img_chunks": 8,
        "lora_resets": 0, "last_rx": now - (now % 5), "rssi": -104, "snr": 5.8, "history": hist,
        "last": {"seq": 219, "lat": 52.297312, "lon": 21.113644, "alt": hist[-1][1], "sat": 11,
                 "fix": 1, "vbe": 7.41, "vbat": 7.38, "imA": 812, "temp": -38.2, "hum": 14.1,
                 "pres": 421.7, "p2": 421.2, "alt2": 6712, "roll": 4.2, "pit": -2.8, "yaw": 0,
                 "ax": 0.1, "ay": 0.7, "az": 9.8, "dsku": 17.2, "dskf": 11.4,
                 "sg0": 212, "sg1": 198, "sg2": 205, "sg3": 221, "ec": [1, 1, 18234, 24310]},
    }


class Card(tk.Frame):
    """Ramka z tytułem i listą par nazwa–wartość."""

    def __init__(self, parent, title: str, rows: list[tuple[str, str]]):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        tk.Label(self, text=title, bg=CARD, fg=BLUE, font=(FONT, 11, "bold"), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="we", padx=12, pady=(8, 4))
        self.columnconfigure(1, weight=1)
        self._val: dict[str, tk.Label] = {}
        for i, (key, name) in enumerate(rows, start=1):
            tk.Label(self, text=name, bg=CARD, fg=DIM, font=(FONT, 10), anchor="w").grid(
                row=i, column=0, sticky="w", padx=(12, 6), pady=1)
            v = tk.Label(self, text="—", bg=CARD, fg=FG, font=(FONT, 12, "bold"), anchor="e")
            v.grid(row=i, column=1, sticky="e", padx=(0, 12), pady=1)
            self._val[key] = v
        tk.Frame(self, bg=CARD, height=6).grid(row=len(rows) + 1, column=0)

    def set(self, key: str, text: str, color: str = FG) -> None:
        self._val[key].config(text=text, fg=DIM if text == "—" else color)


class Chart(tk.Canvas):
    def __init__(self, parent, title: str, unit: str, color: str):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, height=130)
        self._title, self._unit, self._color = title, unit, color

    def draw(self, pts: list[tuple[float, float]]) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        self.create_text(12, 14, text=self._title, anchor="w", fill=BLUE, font=(FONT, 11, "bold"))
        if len(pts) < 2:
            self.create_text(w / 2, h / 2 + 8, text="brak danych", fill=DIM, font=(FONT, 10))
            return
        left, right, top, bottom = 70, w - 14, 30, h - 14
        ys = [p[1] for p in pts]
        lo, hi = min(ys), max(ys)
        if hi - lo < 1:
            lo, hi = lo - 1, hi + 1
        t0, t1 = pts[0][0], pts[-1][0]
        span = max(t1 - t0, 1e-6)
        for y, v in ((top, hi), ((top + bottom) / 2, (lo + hi) / 2), (bottom, lo)):
            self.create_line(left, y, right, y, fill=LINE)
            self.create_text(left - 6, y, text=f"{v:.0f}", anchor="e", fill=DIM, font=(FONT, 9))
        xy = [c for t, v in pts for c in (left + (t - t0) / span * (right - left),
                                          bottom - (v - lo) / (hi - lo) * (bottom - top))]
        self.create_line(*xy, fill=self._color, width=2)
        self.create_text(right, 14, anchor="e", fill=FG, font=(FONT, 10),
                         text=f"{ys[-1]:.0f} {self._unit}   (ostatnie {ago(span)})")


class App(tk.Tk):
    def __init__(self, source):
        super().__init__()
        self._source = source
        self.title("StratoSTEAM — odbiór danych")
        self.configure(bg=BG)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1080, sw - 20)}x{min(720, sh - 80)}")
        self.minsize(760, 520)
        self.bind("<F11>", lambda _e: self.attributes("-fullscreen",
                                                      not self.attributes("-fullscreen")))
        self.bind("<Escape>", lambda _e: self.attributes("-fullscreen", False))
        self._build()
        self._refresh()

    def _build(self) -> None:
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(10, 6))
        self._status = tk.Label(top, text="…", bg=BG, fg=DIM, font=(FONT, 17, "bold"), anchor="w")
        self._status.pack(side="left")
        self._age = tk.Label(top, text="", bg=BG, fg=DIM, font=(FONT, 12), anchor="e")
        self._age.pack(side="right")

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x", padx=8)
        specs = [
            ("gps", "Pozycja (GPS)", [("lat", "Szerokość"), ("lon", "Długość"), ("alt", "Wysokość"),
                                      ("sat", "Satelity"), ("fix", "Fix")]),
            ("radio", "Radio LoRa", [("rssi", "RSSI"), ("snr", "SNR"), ("pk", "Pakiety / straty"),
                                     ("bad", "Uszkodzone"), ("rst", "Resety modułu")]),
            ("pwr", "Zasilanie", [("vbat", "Bateria (INA)"), ("vbe", "Bateria (ESP32)"),
                                  ("imA", "Prąd"), ("w", "Moc"), ("rpi", "RPi na balonie")]),
            ("atm", "Atmosfera", [("temp", "Temperatura"), ("hum", "Wilgotność"), ("pres", "Ciśnienie"),
                                  ("p2", "Ciśnienie 2"), ("alt2", "Wys. z ciśnienia")]),
            ("imu", "Orientacja", [("roll", "Roll"), ("pit", "Pitch"), ("yaw", "Yaw"),
                                   ("g", "Przeciążenie"), ("seq", "Nr pakietu")]),
            ("sg", "Tensometry", [("sg0", "Przód lewy"), ("sg1", "Przód prawy"), ("sg2", "Tył lewy"),
                                  ("sg3", "Tył prawy"), ("sum", "Razem")]),
            ("cam", "Kamery i dysk", [("ok", "ESP32-CAM"), ("rec", "Nagrywanie"), ("fr", "Klatki"),
                                      ("sd", "Karta SD wolne"), ("dsk", "Dysk RPi wolne")]),
            ("stn", "Stacja", [("svc", "Usługa"), ("up", "Działa od"), ("img", "Fragmenty zdjęć"),
                               ("clk", "Zegar"), ("cut", "Pakiet skrócony")]),
        ]
        self._c: dict[str, Card] = {}
        for i, (key, title, rows) in enumerate(specs):
            c = Card(grid, title, rows)
            c.grid(row=i // 4, column=i % 4, sticky="nsew", padx=4, pady=4)
            self._c[key] = c
        for col in range(4):
            grid.columnconfigure(col, weight=1, uniform="k")

        charts = tk.Frame(self, bg=BG)
        charts.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self._alt = Chart(charts, "Wysokość GPS", "m", OK)
        self._rssi = Chart(charts, "Siła sygnału", "dBm", BLUE)
        self._alt.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._rssi.pack(side="left", fill="both", expand=True, padx=(4, 0))

    def _refresh(self) -> None:
        try:
            self._show(self._source())
        finally:
            self.after(REFRESH_MS, self._refresh)

    def _show(self, st: dict | None) -> None:
        now = time.time()
        alive = st is not None and now - st.get("alive", 0) < SERVICE_TIMEOUT_S
        st = st or {}
        p = st.get("last") or {}
        rx = st.get("last_rx")
        age = now - rx if rx else None

        if not alive:
            self._status.config(text="● USŁUGA rpi-ground NIE DZIAŁA", fg=BAD)
        elif age is None:
            self._status.config(text="● NASŁUCH — jeszcze nic nie odebrano", fg=WARN)
        elif age <= FRESH_S:
            self._status.config(text="● ODBIÓR", fg=OK)
        elif age <= STALE_S:
            self._status.config(text="● SŁABY ODBIÓR", fg=WARN)
        else:
            self._status.config(text="● BRAK SYGNAŁU Z BALONU", fg=BAD)
        self._age.config(text=f"ostatni pakiet: {ago(age)} temu" if age is not None else "")

        fix = bool(p.get("fix"))
        g = self._c["gps"]
        g.set("lat", f"{p['lat']:.6f}" if fix else "—")
        g.set("lon", f"{p['lon']:.6f}" if fix else "—")
        g.set("alt", fmt(p.get("alt") if fix else None, "m", 0))
        g.set("sat", fmt(p.get("sat"), "", 0))
        g.set("fix", ("TAK" if fix else "NIE") if p else "—", OK if fix else BAD)

        r = self._c["radio"]
        r.set("rssi", fmt(st.get("rssi"), "dBm", 0))
        r.set("snr", fmt(st.get("snr"), "dB"))
        r.set("pk", f"{st.get('packets', 0)} / {st.get('lost', 0)}" if st else "—")
        r.set("bad", str(st.get("bad", 0)) if st else "—", WARN if st.get("bad") else FG)
        r.set("rst", str(st.get("lora_resets", 0)) if st else "—", BAD if st.get("lora_resets") else FG)

        w = self._c["pwr"]
        vbat, ima = p.get("vbat"), p.get("imA")
        w.set("vbat", fmt(vbat, "V", 2))
        w.set("vbe", fmt(p.get("vbe"), "V", 2))
        w.set("imA", fmt(ima, "mA", 0))
        w.set("w", fmt(vbat * ima / 1000 if vbat is not None and ima is not None else None, "W", 2))
        rpi = "temp" in p
        w.set("rpi", ("działa" if rpi else "brak danych") if p else "—", OK if rpi else WARN)

        a = self._c["atm"]
        a.set("temp", fmt(p.get("temp"), "°C"))
        a.set("hum", fmt(p.get("hum"), "%"))
        a.set("pres", fmt(p.get("pres"), "hPa"))
        a.set("p2", fmt(p.get("p2"), "hPa"))
        a.set("alt2", fmt(p.get("alt2"), "m", 0))

        o = self._c["imu"]
        o.set("roll", fmt(p.get("roll"), "°"))
        o.set("pit", fmt(p.get("pit"), "°"))
        o.set("yaw", fmt(p.get("yaw"), "°"))
        acc = [p.get(k) for k in ("ax", "ay", "az")]
        o.set("g", fmt(math.sqrt(sum(v * v for v in acc)) / 9.80665, "g", 2)
              if None not in acc else "—")
        o.set("seq", fmt(p.get("seq"), "", 0))

        s = self._c["sg"]
        sg = [p.get(f"sg{i}") for i in range(4)]
        for i, v in enumerate(sg):
            s.set(f"sg{i}", fmt(v, "g", 0))
        s.set("sum", fmt(sum(sg), "g", 0) if None not in sg else "—")

        c = self._c["cam"]
        ec = p.get("ec")
        if isinstance(ec, list) and len(ec) >= 4:
            c.set("ok", "działa" if ec[0] else "brak", OK if ec[0] else BAD)
            c.set("rec", "TAK" if ec[1] else "NIE", OK if ec[1] else BAD)
            c.set("fr", str(ec[2]))
            c.set("sd", fmt(ec[3] / 1024, "GB"))
        else:
            for k in ("ok", "rec", "fr", "sd"):
                c.set(k, "—")
        free = p.get("dskf")
        c.set("dsk", fmt(free, "GB"), BAD if free is not None and free < 2 else FG)

        n = self._c["stn"]
        n.set("svc", "działa" if alive else "STOP", OK if alive else BAD)
        n.set("up", ago(now - st["started"]) if alive and st.get("started") else "—")
        n.set("img", str(st.get("img_chunks", 0)) if st else "—")
        n.set("clk", time.strftime("%H:%M:%S"))
        n.set("cut", ("TAK" if p.get("x") else "nie") if p else "—", WARN if p.get("x") else FG)

        hist = st.get("history") or []
        self._alt.draw([(h[0], h[1]) for h in hist if h[1] is not None])
        self._rssi.draw([(h[0], h[2]) for h in hist if h[2] is not None])


if __name__ == "__main__":
    App(demo_state if "--demo" in sys.argv else read_state).mainloop()
