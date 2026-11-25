#!/usr/bin/env python3
"""
StratoSTEAM — okno odbioru na stacji naziemnej (tkinter).

Pokazuje dane odbierane przez usługę rpi-ground (local_feed.py). Samo nie dotyka radia,
więc można je otwierać i zamykać w trakcie lotu.

  python3 gui_odbior.py          normalnie
  python3 gui_odbior.py --demo   udawane dane, bez stacji
"""
import io
import json
import math
import os
import sys
import threading
import time
import tkinter as tk
import urllib.request

from PIL import Image, ImageFile

from config import PREVIEW_URL
from local_feed import PHOTO_PATH, REQUEST_PATH, STATE_PATH

ImageFile.LOAD_TRUNCATED_IMAGES = True      # zdjęcie w trakcie odbioru też pokaż

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
        left, right, top, bottom = 70, w - 14, 34, h - 18
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
                         text=f"{ys[-1]:.0f} {self._unit}")
        self.create_text(right, bottom + 8, anchor="e", fill=DIM, font=(FONT, 8),
                         text=f"ostatnie {ago(span)}")


class LiveFeed(threading.Thread):
    """Pobiera klatki z balonu po sieci w tle, żeby okno nigdy się nie zacinało."""

    def __init__(self, url: str):
        super().__init__(daemon=True)
        self._url = url
        self.frame: tuple[float, bytes] | None = None      # (czas, JPEG)
        self.enabled = True

    def run(self) -> None:
        while True:
            delay = 1.0
            if self.enabled:
                try:
                    with urllib.request.urlopen(self._url, timeout=3) as r:
                        self.frame = (time.time(), r.read(2_000_000))
                except (OSError, ValueError):
                    delay = 5.0
            time.sleep(delay)


class Photo(tk.Frame):
    """Obraz z kamery: na żywo po sieci, a gdy jej nie ma — ostatnie zdjęcie z LoRa."""

    LIVE_S = 12

    def __init__(self, parent, live: LiveFeed):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        self._live = live
        self._shown = None          # klucz ostatnio narysowanego obrazu
        self._img = None            # referencja, inaczej Tk usunie obraz
        self._big: tk.Toplevel | None = None
        head = tk.Frame(self, bg=CARD)
        head.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(head, text="Kamera", bg=CARD, fg=BLUE, font=(FONT, 11, "bold")).pack(side="left")
        self._btn = tk.Button(head, text="Zrób zdjęcie (LoRa)", command=self._request, bg="#21262d",
                              fg=FG, activebackground=LINE, activeforeground=FG, relief="flat",
                              font=(FONT, 9), padx=8, pady=1)
        self._btn.pack(side="right")
        self._info = tk.Label(self, text="", bg=CARD, fg=DIM, font=(FONT, 9), anchor="w")
        self._info.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        self._view = tk.Canvas(self, bg=BG, highlightthickness=0, width=200, height=100, cursor="hand2")
        self._view.pack(fill="both", expand=True, padx=8, pady=2)
        self._view.bind("<Button-1>", lambda _e: self._toggle_big())

    def _request(self) -> None:
        try:
            with open(REQUEST_PATH, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError as e:
            self._info.config(text=f"nie mogę wysłać prośby: {e}", fg=BAD)

    def _toggle_big(self) -> None:
        if self._big is not None and self._big.winfo_exists():
            self._big.destroy()
            self._big = None
            return
        self._big = tk.Toplevel(self, bg=BG)
        self._big.title("StratoSTEAM — kamera")
        self._big.geometry("960x560")
        c = tk.Canvas(self._big, bg=BG, highlightthickness=0)
        c.pack(fill="both", expand=True)
        c.bind("<Button-1>", lambda _e: self._toggle_big())
        self._big.canvas = c
        self._shown = None

    def refresh(self, st: dict) -> None:
        now = time.time()
        ph = st.get("photo")
        frame = self._live.frame
        if frame and now - frame[0] < self.LIVE_S:
            jpeg, key = frame[1], ("live", frame[0])
            text, color = f"● NA ŻYWO przez sieć ({ago(now - frame[0])} temu)", OK
        else:
            jpeg, key = None, None
            try:
                key = ("lora", os.path.getmtime(PHOTO_PATH))
                with open(PHOTO_PATH, "rb") as f:
                    jpeg = f.read()
            except OSError:
                pass
            if ph:
                state = "komplet" if ph["done"] else f"odbieram {ph['got']}/{ph['total']}"
                text, color = f"zdjęcie LoRa: {state}, {ago(now - ph['ts'])} temu", \
                    OK if ph["done"] else WARN
            else:
                text, color = "brak sieci i zdjęć z LoRa", DIM
        if os.path.exists(REQUEST_PATH):
            text, color = "prośba czeka na pakiet z balonu…", WARN
        elif st.get("photo_req"):
            text, color = f"prośba wysłana {ago(now - st['photo_req'])} temu, czekam na zdjęcie", WARN
        self._info.config(text=text, fg=color)

        big = self._big if self._big is not None and self._big.winfo_exists() else None
        size = (self._view.winfo_width(), self._view.winfo_height(),
                big.canvas.winfo_width() if big else 0, big.canvas.winfo_height() if big else 0)
        if jpeg is None or (key, size) == self._shown:
            return
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        except Exception:       # uszkodzony JPEG z radia nie może wywrócić okna
            return
        self._shown = (key, size)
        self._img = [self._draw(c, img) for c in ([self._view] + ([big.canvas] if big else []))]

    @staticmethod
    def _draw(canvas: tk.Canvas, img: Image.Image) -> tk.PhotoImage:
        w, h = max(canvas.winfo_width(), 32), max(canvas.winfo_height(), 18)
        k = min(w / img.width, h / img.height)
        fit = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
        buf = io.BytesIO()
        fit.save(buf, format="PPM")     # PPM, bo ImageTk bywa niezainstalowany
        photo = tk.PhotoImage(data=buf.getvalue(), format="PPM")
        canvas.delete("all")
        canvas.create_image(w // 2, h // 2, image=photo)
        return photo


class App(tk.Tk):
    def __init__(self, source):
        super().__init__()
        self._source = source
        self._live = LiveFeed(PREVIEW_URL)
        self._live.start()
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
        self._photo = Photo(charts, self._live)
        for col, w in enumerate((self._alt, self._rssi, self._photo)):
            w.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 0 if col == 2 else 4))
            charts.columnconfigure(col, weight=1, uniform="c")
        charts.rowconfigure(0, weight=1)

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
        self._photo.refresh(st)


if __name__ == "__main__":
    App(demo_state if "--demo" in sys.argv else read_state).mainloop()
