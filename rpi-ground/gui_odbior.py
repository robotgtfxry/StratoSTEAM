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
from tkinter import messagebox
import urllib.request

from PIL import Image

from config import PREVIEW_URL
from local_feed import AUTO_PATH, AUTO_S, CMD_DIR, MAX_TRIES, PHOTO_PATH, REQUEST_PATH, STATE_PATH
from mission import ASCENT, DESCENT, LANDED, MANUAL, PREP, START, preflight


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
        "started": now - 4000, "alive": now, "packets": 212, "bad": 1, "lost": 6,
        "mission": {"phase": ASCENT, "t0": now - 1234, "alt0": 120, "max_alt": hist[-1][1],
                    "alt": hist[-1][1], "vs": 5.1, "src": "GPS", "manual": {},
                    "events": [[now - 1234, "START wciśnięty"], [now - 1190, "Balon się wznosi"]]},
        "lora_resets": 0, "last_rx": now - (now % 5), "rssi": -104, "snr": 5.8, "history": hist,
        "last": {"seq": 219, "cs": "SP8DEV-1", "lat": 52.297312, "lon": 21.113644, "alt": hist[-1][1], "sat": 11, "gview": 17, "gsnr": 43,
                 "fix": 1, "vbe": 7.41, "vbat": 7.38, "imA": 812, "tcpu": 66, "temp": -38.2, "hum": 14.1,
                 "pres": 421.7, "p2": 421.2, "alt2": 6712, "roll": 4.2, "pit": -2.8, "yaw": 0,
                 "ax": 0.1, "ay": 0.7, "az": 9.8, "dsku": 17.2, "dskf": 11.4,
                 "ec": [1, 1, 18234, 24310]},
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
                row=i, column=0, sticky="w", padx=(12, 4), pady=1)
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


def send_cmd(c: dict) -> None:
    """Polecenie dla usługi rpi-ground."""
    os.makedirs(CMD_DIR, exist_ok=True)
    path = os.path.join(CMD_DIR, f"{time.time():.6f}.json")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(c, f)
    os.replace(path + ".tmp", path)


def clock(seconds: float) -> str:
    s = int(abs(seconds))
    return f"T{'-' if seconds < 0 else '+'}{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


PHASE_LOOK = {PREP: ("PRZYGOTOWANIE", DIM), START: ("START — czekam na wznoszenie", WARN),
              ASCENT: ("▲ LOT: WZNOSZENIE", OK), DESCENT: ("▼ LOT: OPADANIE", BLUE),
              LANDED: ("■ WYLĄDOWAŁ", WARN)}


class MissionBar(tk.Frame):
    """Pasek fazy misji nad danymi."""

    def __init__(self, parent, on_open):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        self._phase = tk.Label(self, text="", bg=CARD, fg=DIM, font=(FONT, 15, "bold"))
        self._phase.pack(side="left", padx=12, pady=5)
        self._clock = tk.Label(self, text="", bg=CARD, fg=FG, font=(FONT, 15, "bold"))
        self._clock.pack(side="left", padx=8)
        tk.Button(self, text="Procedura startu", command=on_open, bg="#238636", fg="white",
                  activebackground=OK, activeforeground="white", relief="flat",
                  font=(FONT, 10, "bold"), padx=10).pack(side="right", padx=10, pady=4)
        self._buz_on = False
        self._buz = tk.Button(self, text="Buzzer: włącz", command=self._toggle_buz, **self._BTN)
        self._buz.pack(side="right", padx=(0, 4), pady=4)
        tk.Button(self, text="Buzzer 5 s", command=lambda: send_cmd(
            {"a": "buzzer", "on": True, "ms": 5000}), **self._BTN).pack(side="right", padx=4, pady=4)
        self._buz_info = tk.Label(self, text="", bg=CARD, fg=WARN, font=(FONT, 9))
        self._buz_info.pack(side="right", padx=4)
        self._info = tk.Label(self, text="", bg=CARD, fg=DIM, font=(FONT, 10))
        self._info.pack(side="left", padx=8)

    _BTN = dict(bg="#21262d", fg=FG, activebackground=LINE, activeforeground=FG, relief="flat",
                font=(FONT, 10), padx=8)

    def _toggle_buz(self) -> None:
        self._buz_on = not self._buz_on
        send_cmd({"a": "buzzer", "on": self._buz_on})
        self._buz.config(text="Buzzer: WYŁĄCZ" if self._buz_on else "Buzzer: włącz",
                         fg=WARN if self._buz_on else FG)

    def refresh(self, st: dict, now: float) -> None:
        b = st.get("buzzer")
        self._buz_info.config(text=f"buzzer {b['text']}" if b and now - b["ts"] < 20 else "")
        m = st.get("mission") or {}
        text, color = PHASE_LOOK.get(m.get("phase"), ("—", DIM))
        self._phase.config(text=text, fg=color)
        self._clock.config(text=clock(now - m["t0"]) if m.get("t0") else "T−")
        bits = []
        if m.get("alt") is not None:
            bits.append(f"{m['alt']:.0f} m ({m.get('src')})")
        if m.get("vs") is not None:
            bits.append(f"{m['vs']:+.1f} m/s")
        if m.get("max_alt") is not None and m.get("phase") != PREP:
            bits.append(f"szczyt {m['max_alt']:.0f} m")
        self._info.config(text="   ".join(bits))


class Procedure(tk.Toplevel):
    """Lista kontrolna i przycisk START."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.title("StratoSTEAM — procedura startu")
        self.geometry("620x800")
        self._st: dict = {}
        self._auto_rows: list[tuple[tk.Label, tk.Label, tk.Label]] = []
        self._manual: dict[str, tk.BooleanVar] = {}
        self._synced = False
        box = self._box("Sprawdzenia automatyczne")
        for _ in preflight({}, 0):
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x", padx=10, pady=1)
            mark = tk.Label(row, text="?", bg=CARD, fg=DIM, width=2, font=(FONT, 11, "bold"))
            name = tk.Label(row, text="", bg=CARD, fg=FG, font=(FONT, 10), anchor="w")
            val = tk.Label(row, text="", bg=CARD, fg=DIM, font=(FONT, 10), anchor="e")
            mark.pack(side="left")
            name.pack(side="left", fill="x", expand=True)
            val.pack(side="right")
            self._auto_rows.append((mark, name, val))
        box = self._box("Sprawdzenia ręczne")
        for key, text in MANUAL:
            v = self._manual[key] = tk.BooleanVar()
            tk.Checkbutton(box, text=text, variable=v, bg=CARD, fg=FG, selectcolor=BG, anchor="w",
                           activebackground=CARD, activeforeground=FG, highlightthickness=0, bd=0,
                           font=(FONT, 10), command=lambda k=key, v=v: send_cmd(
                               {"a": "manual", "k": k, "v": v.get()})).pack(fill="x", padx=10, pady=1)
        self._sum = tk.Label(self, text="", bg=BG, fg=DIM, font=(FONT, 12, "bold"))
        self._sum.pack(pady=(8, 4))
        btns = tk.Frame(self, bg=BG)
        btns.pack(pady=4)
        self._start = tk.Button(btns, text="START", command=self._go, font=(FONT, 18, "bold"),
                                relief="flat", padx=40, pady=6, fg="white", bg="#238636",
                                activebackground=OK, activeforeground="white")
        self._start.pack(side="left", padx=6)
        tk.Button(btns, text="Nowa procedura", command=self._reset, font=(FONT, 10), relief="flat",
                  bg="#21262d", fg=FG, activebackground=LINE, activeforeground=FG,
                  padx=10, pady=6).pack(side="left", padx=6)
        self._log = tk.Label(self, text="", bg=BG, fg=DIM, font=(FONT, 9), justify="left", anchor="w")
        self._log.pack(fill="x", padx=14, pady=6)

    def _box(self, title: str) -> tk.Frame:
        f = tk.Frame(self, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        f.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(f, text=title, bg=CARD, fg=BLUE, font=(FONT, 11, "bold"), anchor="w").pack(
            fill="x", padx=10, pady=(6, 2))
        return f

    def _missing(self) -> list[str]:
        out = [name for name, ok, _ in preflight(self._st, time.time()) if not ok]
        return out + [text for k, text in MANUAL if not self._manual[k].get()]

    def _go(self) -> None:
        missing = self._missing()
        note = f"\n\nWłączy też automatyczne zdjęcia co {AUTO_S // 60} min."
        msg = f"Wszystkie sprawdzenia OK. Rozpocząć misję?{note}" if not missing else \
            "NIE SPEŁNIONE:\n\n• " + "\n• ".join(missing) + f"\n\nRozpocząć mimo to?{note}"
        ask = messagebox.askyesno if not missing else \
            (lambda t, m, parent: messagebox.askyesno(t, m, parent=parent, icon="warning", default="no"))
        if ask("START misji", msg, parent=self):
            send_cmd({"a": "start", "skipped": missing})

    def _reset(self) -> None:
        if messagebox.askyesno("Nowa procedura", "Wyzerować fazę misji, zegar i listę kontrolną?",
                               parent=self, icon="warning", default="no"):
            send_cmd({"a": "reset"})
            self._synced = False

    def refresh(self, st: dict, now: float) -> None:
        self._st = st
        m = st.get("mission") or {}
        if not self._synced and m:
            for k, v in self._manual.items():
                v.set(bool(m.get("manual", {}).get(k)))
            self._synced = True
        for (mark, name, val), (text, ok, value) in zip(self._auto_rows, preflight(st, now)):
            mark.config(text="✔" if ok else "✘" if ok is False else "?",
                        fg=OK if ok else BAD if ok is False else DIM)
            name.config(text=text)
            val.config(text=value)
        missing = len(self._missing())
        prep = m.get("phase") == PREP
        self._sum.config(text=("GOTOWY DO STARTU" if not missing else f"Brakuje: {missing}") if prep
                         else PHASE_LOOK.get(m.get("phase"), ("", DIM))[0],
                         fg=(OK if not missing else WARN) if prep else OK)
        self._start.config(state="normal" if prep else "disabled",
                           bg="#238636" if prep and not missing else "#9e6a03" if prep else "#21262d")
        ev = (m.get("events") or [])[-5:]
        self._log.config(text="\n".join(time.strftime("%H:%M:%S", time.localtime(t)) + "  " + x for t, x in ev))


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
        self._btn = tk.Button(head, text="Zrób zdjęcie", command=self._request, bg="#21262d",
                              fg=FG, activebackground=LINE, activeforeground=FG, relief="flat",
                              font=(FONT, 9), padx=8, pady=1)
        self._btn.pack(side="right")
        self._auto = tk.BooleanVar(value=os.path.exists(AUTO_PATH))
        tk.Checkbutton(head, text=f"auto co {AUTO_S // 60} min", variable=self._auto,
                       command=self._set_auto, bg=CARD, fg=DIM, selectcolor=BG, font=(FONT, 9),
                       activebackground=CARD, activeforeground=FG, highlightthickness=0,
                       bd=0).pack(side="right", padx=8)
        self._live_on = tk.BooleanVar(value=not os.path.exists(PHOTO_PATH))
        tk.Checkbutton(head, text="na żywo", variable=self._live_on, bg=CARD, fg=DIM, selectcolor=BG,
                       font=(FONT, 9), activebackground=CARD, activeforeground=FG,
                       highlightthickness=0, bd=0).pack(side="right")
        self._bar = tk.Canvas(self, bg=LINE, height=5, highlightthickness=0)
        self._bar.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        self._info = tk.Label(self, text="", bg=CARD, fg=DIM, font=(FONT, 9), anchor="w")
        self._info.pack(side="bottom", fill="x", padx=12, pady=(0, 4))
        self._view = tk.Canvas(self, bg=BG, highlightthickness=0, width=200, height=100, cursor="hand2")
        self._view.pack(fill="both", expand=True, padx=8, pady=2)
        self._view.bind("<Button-1>", lambda _e: self._toggle_big())

    def _request(self) -> None:
        self._live_on.set(False)
        try:
            with open(REQUEST_PATH, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except OSError as e:
            self._info.config(text=f"nie mogę wysłać prośby: {e}", fg=BAD)

    def _set_auto(self) -> None:
        try:
            if self._auto.get():
                open(AUTO_PATH, "w").close()
            else:
                os.remove(AUTO_PATH)
        except OSError:
            pass

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
        self._auto.set(os.path.exists(AUTO_PATH))       # START i lądowanie też to przełączają
        ph = st.get("photo")
        frame = self._live.frame
        if self._live_on.get() and frame and now - frame[0] < self.LIVE_S:
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
                kb = f"{ph['bytes'] / 1024:.1f} kB"
                if ph["done"]:
                    text, color = f"zdjęcie LoRa: całe, {kb}, {ago(now - ph['ts'])} temu", OK
                elif ph["failed"]:
                    text, color = f"nie udało się: {ph['got']}/{ph['total']} pakietów", BAD
                else:
                    text, color = f"odbieram {ph['got']}/{ph['total']} pakietów ({kb})…", WARN
            else:
                text, color = "brak sieci i zdjęć z LoRa", DIM
        if os.path.exists(REQUEST_PATH):
            text, color = "prośba czeka na pakiet z balonu…", WARN
        elif st.get("photo_req"):
            text, color = (f"prośba {st.get('photo_try', 1)}/{MAX_TRIES} wysłana "
                           f"{ago(now - st['photo_req'])} temu"), WARN
        elif st.get("photo_fail"):
            text, color = "RPi balonu nie odsyła zdjęcia (kabel USB do S3?)", BAD
        self._info.config(text=text, fg=color)
        self._live.enabled = self._live_on.get()
        self._bar.delete("all")
        if ph and not ph["done"] and not ph["failed"] and ph["total"]:
            self._bar.create_rectangle(0, 0, self._bar.winfo_width() * ph["got"] / ph["total"], 6,
                                       fill=WARN, width=0)

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
        self.geometry(f"{min(1280, sw - 20)}x{min(920, sh - 70)}")
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

        self._proc: Procedure | None = None
        self._mission = MissionBar(self, self._open_proc)
        self._mission.pack(fill="x", padx=12, pady=(0, 4))

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x", padx=8)
        specs = [
            ("gps", "Pozycja (GPS)", [("lat", "Szerokość"), ("lon", "Długość"), ("alt", "Wysokość"),
                                      ("sat", "Satelity"), ("snr", "Sygnał GPS"), ("fix", "Fix")]),
            ("radio", "Radio LoRa", [("rssi", "RSSI"), ("snr", "SNR"), ("pk", "Pakiety/straty"),
                                     ("bad", "Uszkodzone"), ("rst", "Resety modułu"),
                                     ("cs", "Znak sondy")]),
            ("pwr", "Zasilanie", [("vbat", "Bateria (INA)"), ("vbe", "Bateria (ESP32)"),
                                  ("imA", "Prąd"), ("w", "Moc"), ("rpi", "RPi na balonie"),
                                  ("cpu", "Temperatura RPi")]),
            ("atm", "Atmosfera", [("temp", "Temperatura"), ("hum", "Wilgotność"), ("pres", "Ciśnienie"),
                                  ("p2", "Ciśnienie 2"), ("alt2", "Wys. z ciśnienia")]),
            ("imu", "Orientacja", [("roll", "Roll"), ("pit", "Pitch"), ("yaw", "Yaw"),
                                   ("g", "Przeciążenie"), ("seq", "Nr pakietu")]),
            ("cam", "Kamery i dysk", [("ok", "ESP32-CAM"), ("rec", "Nagrywanie"), ("fr", "Klatki"),
                                      ("sd", "Karta SD wolne"), ("dsk", "Dysk RPi wolne")]),
            ("stn", "Stacja", [("svc", "Usługa"), ("up", "Działa od"), ("clk", "Zegar"), ("cut", "Pakiet skrócony")]),
        ]
        self._c: dict[str, Card] = {}
        for i, (key, title, rows) in enumerate(specs):
            c = Card(grid, title, rows)
            last = i == len(specs) - 1      # ostatnia karta wypełnia resztę wiersza
            c.grid(row=i // 4, column=i % 4, columnspan=4 - i % 4 if last else 1,
                   sticky="nsew", padx=4, pady=4)
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
            charts.columnconfigure(col, weight=2 if col == 2 else 1, uniform="c")
        charts.rowconfigure(0, weight=1)

    def _open_proc(self) -> None:
        if self._proc is not None and self._proc.winfo_exists():
            self._proc.lift()
            return
        self._proc = Procedure(self)

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
        g.set("sat", f"{p['sat']} z {p['gview']}" if "gview" in p else fmt(p.get("sat"), "", 0))
        snr = p.get("gsnr")
        g.set("snr", fmt(snr, "dBHz", 0), OK if (snr or 0) >= 30 else WARN if snr else BAD)
        g.set("fix", ("TAK" if fix else "NIE") if p else "—", OK if fix else BAD)

        r = self._c["radio"]
        r.set("rssi", fmt(st.get("rssi"), "dBm", 0))
        r.set("snr", fmt(st.get("snr"), "dB"))
        r.set("pk", f"{st.get('packets', 0)} / {st.get('lost', 0)}" if st else "—")
        r.set("bad", str(st.get("bad", 0)) if st else "—", WARN if st.get("bad") else FG)
        r.set("rst", str(st.get("lora_resets", 0)) if st else "—", BAD if st.get("lora_resets") else FG)
        r.set("cs", p.get("cs") or "—", FG if p.get("cs") else WARN)

        w = self._c["pwr"]
        vbat, ima = p.get("vbat"), p.get("imA")
        w.set("vbat", fmt(vbat, "V", 2))
        w.set("vbe", fmt(p.get("vbe"), "V", 2))
        w.set("imA", fmt(ima, "mA", 0))
        w.set("w", fmt(vbat * ima / 1000 if vbat is not None and ima is not None else None, "W", 2))
        rpi = "temp" in p
        w.set("rpi", ("działa" if rpi else "brak danych") if p else "—", OK if rpi else WARN)

        cpu = p.get("tcpu")              # RPi 5 zwalnia od 80 °C
        w.set("cpu", fmt(cpu, "°C", 0), FG if cpu is None else BAD if cpu >= 80 else WARN if cpu >= 70 else OK)

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
        n.set("clk", time.strftime("%H:%M:%S"))
        n.set("cut", ("TAK" if p.get("x") else "nie") if p else "—", WARN if p.get("x") else FG)

        hist = st.get("history") or []
        self._alt.draw([(h[0], h[1]) for h in hist if h[1] is not None])
        self._rssi.draw([(h[0], h[2]) for h in hist if h[2] is not None])
        self._photo.refresh(st)
        self._mission.refresh(st, now)
        if self._proc is not None and self._proc.winfo_exists():
            self._proc.refresh(st, now)


if __name__ == "__main__":
    App(demo_state if "--demo" in sys.argv else read_state).mainloop()
