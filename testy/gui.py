"""
StratoSTEAM — Tester czujników (tkinter).

Po lewej lista całego sprzętu, po prawej: opis, instrukcja podłączenia do
Raspberry Pi 5, rysunek złącza 40-pin z podświetlonymi pinami i wynik testu.
"""
from __future__ import annotations

import datetime
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import catalog
import hw_tests as T
import pinout
from repo import REPO_ROOT, pi_model

# ── paleta ───────────────────────────────────────────────────────────────────
BG = "#0e1620"
PANEL = "#152030"
CARD = "#1b2838"
LINE = "#26374d"
FG = "#e7eef7"
MUTED = "#90a4bd"
ACCENT = "#4aa3ff"

STATUS_COLOR = {
    T.OK: "#3ecf8e",
    T.WARN: "#f0b429",
    T.FAIL: "#ff6058",
    T.MISSING: "#93a7c0",
    T.INFO: "#4aa3ff",
    T.PENDING: "#5b6e86",
}
STATUS_TEXT = {
    T.OK: "DZIAŁA",
    T.WARN: "UWAGA",
    T.FAIL: "BŁĄD",
    T.MISSING: "BRAK BIBLIOTEKI",
    T.INFO: "SPRAWDŹ RĘCZNIE",
    T.PENDING: "nietestowany",
}
KIND_COLOR = {
    catalog.K_3V3: "#f0a92e",
    catalog.K_5V: "#ff6058",
    catalog.K_GND: "#7c8ea6",
    catalog.K_SIG: "#4aa3ff",
    catalog.K_OTHER: "#90a4bd",
}
KIND_NAME = {
    catalog.K_3V3: "3.3 V",
    catalog.K_5V: "5 V",
    catalog.K_GND: "masa",
    catalog.K_SIG: "sygnał",
    catalog.K_OTHER: "poza złączem",
}

F_TITLE = ("Segoe UI", 15, "bold")
F_H1 = ("Segoe UI", 12, "bold")
F_H2 = ("Segoe UI", 10, "bold")
F_BODY = ("Segoe UI", 9)
F_MONO = ("Consolas", 9)
F_PIN = ("Consolas", 7)

LIVE_INTERVAL_MS = 2000


def _init_fonts() -> None:
    """Dobiera kroje pod system — na Raspberry Pi OS nie ma Segoe UI ani Consolas."""
    global F_TITLE, F_H1, F_H2, F_BODY, F_MONO, F_PIN
    from tkinter import font as tkfont

    families = set(tkfont.families())

    def pick(candidates: tuple[str, ...], named: str) -> str:
        for name in candidates:
            if name in families:
                return name
        return tkfont.nametofont(named).actual("family")

    ui = pick(("Segoe UI", "DejaVu Sans", "Noto Sans", "Cantarell"), "TkDefaultFont")
    mono = pick(("Consolas", "DejaVu Sans Mono", "Liberation Mono", "Courier New"),
                "TkFixedFont")
    F_TITLE, F_H1, F_H2 = (ui, 15, "bold"), (ui, 12, "bold"), (ui, 10, "bold")
    F_BODY, F_MONO, F_PIN = (ui, 9), (mono, 9), (mono, 7)


class ScrollArea(tk.Frame):
    """Pionowo przewijalny obszar — cała prawa kolumna z opisem."""

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.body = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.body.bind("<Configure>",
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        for w in (self.canvas, self.body):
            w.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
            w.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def to_top(self):
        self.canvas.yview_moveto(0.0)


class TesterApp:
    def __init__(self, root: tk.Tk, simulate: bool = False):
        self.root = root
        self.devices = catalog.DEVICES
        self.results: dict[str, T.Result] = {}
        self.current: catalog.Device | None = None
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self.live_job: str | None = None
        self.sim_var = tk.BooleanVar(value=simulate)
        self.live_var = tk.BooleanVar(value=False)
        self.wrap = 460          # szerokość zawijania tekstu, zmienia się z oknem
        T.set_simulation(simulate)

        _init_fonts()
        root.title("StratoSTEAM — Tester czujników")
        w = min(1240, root.winfo_screenwidth() - 40)
        h = min(800, root.winfo_screenheight() - 80)
        root.geometry(f"{max(w, 800)}x{max(h, 560)}")
        root.minsize(900, 560)
        root.configure(bg=BG)

        self._init_style()
        self._build_header()
        self._build_body()
        self._build_statusbar()
        self._fill_tree()
        self.root.after(120, self._poll_queue)
        if self.devices:
            self._select_device(self.devices[0].id)

    # ── styl ─────────────────────────────────────────────────────────────────
    def _init_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=FG,
                        rowheight=26, borderwidth=0, font=F_BODY)
        style.configure("Treeview.Heading", background=PANEL, foreground=MUTED,
                        borderwidth=0, font=F_H2)
        style.map("Treeview", background=[("selected", "#27456b")],
                  foreground=[("selected", FG)])
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED)
        style.configure("TCheckbutton", background=PANEL, foreground=FG, font=F_BODY)
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("active", FG)])

    # ── nagłówek ─────────────────────────────────────────────────────────────
    def _build_header(self):
        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(side="top", fill="x")
        left = tk.Frame(bar, bg=PANEL)
        left.pack(side="left", padx=14, pady=10)
        tk.Label(left, text="StratoSTEAM — Tester czujników", font=F_TITLE,
                 bg=PANEL, fg=FG).pack(anchor="w")
        model = pi_model() or "brak Raspberry Pi (uruchom test w trybie symulacji)"
        tk.Label(left, text=f"Wykryta płytka: {model}", font=F_BODY,
                 bg=PANEL, fg=MUTED).pack(anchor="w")

        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", padx=14, pady=10)
        ttk.Checkbutton(right, text="Tryb symulacji (bez sprzętu)", variable=self.sim_var,
                        command=self._toggle_sim).pack(side="left", padx=(0, 12))
        self._button(right, "Testuj wszystko", self.run_all, ACCENT).pack(side="left", padx=4)
        self._button(right, "Zapisz raport", self.save_report, CARD).pack(side="left", padx=4)

    def _button(self, parent, text, command, bg, fg=None):
        return tk.Button(parent, text=text, command=command, font=F_H2,
                         bg=bg, fg=fg or ("#0b1017" if bg == ACCENT else FG),
                         activebackground=bg, activeforeground=FG,
                         relief="flat", bd=0, padx=14, pady=6, cursor="hand2")

    # ── główna część ─────────────────────────────────────────────────────────
    def _build_body(self):
        body = tk.Frame(self.root, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        # lewa kolumna — lista sprzętu
        left = tk.Frame(body, bg=PANEL, width=360)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="SPRZĘT", font=F_H2, bg=PANEL, fg=MUTED,
                 anchor="w").pack(fill="x", padx=14, pady=(12, 6))
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.column("#0", width=340, minwidth=200, stretch=True)
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        for status, color in STATUS_COLOR.items():
            self.tree.tag_configure(f"st_{status}", foreground=color)
        self.tree.tag_configure("group", foreground=MUTED, font=F_H2)

        # prawa kolumna — szczegóły + rysunek złącza
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        # kolejność ma znaczenie: panel złącza rezerwuje swoją szerokość jako pierwszy,
        # dopiero potem opis zajmuje resztę
        pinbox = tk.Frame(right, bg=PANEL, width=340)
        pinbox.pack(side="right", fill="y")
        pinbox.pack_propagate(False)
        self.details = ScrollArea(right)
        self.details.pack(side="left", fill="both", expand=True)
        self.details.canvas.bind("<Configure>", self._on_details_resize, add="+")
        tk.Label(pinbox, text="ZŁĄCZE 40-PIN RASPBERRY PI 5", font=F_H2, bg=PANEL,
                 fg=MUTED).pack(fill="x", padx=12, pady=(12, 2))
        tk.Label(pinbox, text="widok z góry, pin 1 w lewym górnym rogu\n"
                              "(przy gnieździe kart microSD)",
                 font=F_BODY, bg=PANEL, fg=MUTED, justify="left").pack(fill="x", padx=12)
        self.pin_canvas = tk.Canvas(pinbox, bg=PANEL, highlightthickness=0, width=320)
        self.pin_canvas.pack(padx=6, pady=6, fill="both", expand=True)
        self.pin_canvas.bind("<Configure>", lambda e: self._draw_header_pins(), add="+")
        self.legend = tk.Frame(pinbox, bg=PANEL)
        self.legend.pack(fill="x", padx=12, pady=(0, 10))
        for kind in (catalog.K_3V3, catalog.K_5V, catalog.K_GND, catalog.K_SIG):
            row = tk.Frame(self.legend, bg=PANEL)
            row.pack(anchor="w")
            tk.Canvas(row, width=12, height=12, bg=PANEL, highlightthickness=0).pack(side="left")
            row.winfo_children()[-1].create_oval(2, 2, 11, 11, fill=KIND_COLOR[kind], outline="")
            tk.Label(row, text=KIND_NAME[kind], font=F_BODY, bg=PANEL,
                     fg=MUTED).pack(side="left", padx=6)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL)
        bar.pack(side="bottom", fill="x")
        self.status_label = tk.Label(bar, text="Gotowy", font=F_BODY, bg=PANEL, fg=MUTED,
                                     anchor="w")
        self.status_label.pack(side="left", padx=14, pady=6)
        self.summary_label = tk.Label(bar, text="", font=F_BODY, bg=PANEL, fg=MUTED,
                                      anchor="e")
        self.summary_label.pack(side="right", padx=14, pady=6)

    # ── lista sprzętu ────────────────────────────────────────────────────────
    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for group in catalog.GROUPS:
            items = [d for d in self.devices if d.group == group]
            if not items:
                continue
            node = self.tree.insert("", "end", iid=f"g_{group}", text=f"  {group}",
                                    open=True, tags=("group",))
            for dev in items:
                self.tree.insert(node, "end", iid=dev.id, text=f"     ○  {dev.name}",
                                 tags=(f"st_{T.PENDING}",))

    def _refresh_tree_item(self, device_id: str):
        res = self.results.get(device_id)
        status = res.status if res else T.PENDING
        marks = {T.OK: "●", T.WARN: "▲", T.FAIL: "✕", T.MISSING: "◌",
                 T.INFO: "◆", T.PENDING: "○"}
        dev = catalog.BY_ID[device_id]
        self.tree.item(device_id, text=f"     {marks[status]}  {dev.name}",
                       tags=(f"st_{status}",))
        done = len(self.results)
        okc = sum(1 for r in self.results.values() if r.status == T.OK)
        bad = sum(1 for r in self.results.values() if r.status in (T.FAIL, T.WARN))
        self.summary_label.config(
            text=f"przetestowane: {done}/{len(self.devices)}   działa: {okc}   do sprawdzenia: {bad}")

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel or sel[0] not in catalog.BY_ID:
            return
        if self.current is not None and self.current.id == sel[0]:
            return                      # selection_set poniżej odbija to zdarzenie z powrotem
        self._select_device(sel[0])

    def _select_device(self, device_id: str):
        self._stop_live()
        self.current = catalog.BY_ID[device_id]
        if self.tree.selection() != (device_id,):
            self.tree.selection_set(device_id)
        self._render_details()
        self._draw_header_pins()
        self.details.to_top()

    # ── panel szczegółów ─────────────────────────────────────────────────────
    def _render_details(self):
        dev = self.current
        if dev is None:
            return
        self.details.clear()
        body = self.details.body

        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(head, text=dev.name, font=F_TITLE, bg=BG, fg=FG,
                 wraplength=self.wrap, justify="left").pack(anchor="w")
        res = self.results.get(dev.id)
        status = res.status if res else T.PENDING
        pill = tk.Label(head, text=STATUS_TEXT[status], font=F_H2, bg=BG,
                        fg=STATUS_COLOR[status])
        pill.pack(anchor="w", pady=(2, 0))
        tk.Label(head, text=f"{dev.group}   •   {dev.bus}   •   czas testu: {dev.duration}",
                 font=F_BODY, bg=BG, fg=MUTED, wraplength=self.wrap, justify="left"
                 ).pack(anchor="w", pady=(4, 0))
        tk.Label(head, text=dev.summary, font=F_BODY, bg=BG, fg=FG, justify="left",
                 wraplength=self.wrap).pack(anchor="w", pady=(8, 0))

        self._section(body, "JAK PODŁĄCZYĆ")
        steps = tk.Frame(body, bg=BG)
        steps.pack(fill="x", padx=18)
        for i, step in enumerate(dev.steps, 1):
            row = tk.Frame(steps, bg=BG)
            row.pack(fill="x", anchor="w", pady=1)
            tk.Label(row, text=f"{i}.", font=F_H2, bg=BG, fg=ACCENT, width=3,
                     anchor="w").pack(side="left")
            tk.Label(row, text=step, font=F_BODY, bg=BG, fg=FG, justify="left",
                     wraplength=self.wrap - 40, anchor="w").pack(side="left", fill="x")

        self._section(body, "POŁĄCZENIA")
        table = tk.Frame(body, bg=LINE)
        table.pack(fill="x", padx=18)
        for col, weight in ((0, 3), (1, 3), (2, 4)):
            table.columnconfigure(col, weight=weight, uniform="wiring")
        self._table_row(table, 0, "Sygnał modułu", "Gdzie na Raspberry Pi 5", "Uwagi",
                        header=True)
        for i, w in enumerate(dev.wiring, 1):
            self._table_row(table, i, w.signal, w.target, w.note,
                            color=KIND_COLOR.get(w.kind, FG))

        if dev.notes:
            self._section(body, "WARTO WIEDZIEĆ")
            notes = tk.Frame(body, bg=BG)
            notes.pack(fill="x", padx=18)
            for note in dev.notes:
                row = tk.Frame(notes, bg=BG)
                row.pack(fill="x", anchor="w", pady=1)
                tk.Label(row, text="•", font=F_BODY, bg=BG, fg=ACCENT, width=3,
                         anchor="w").pack(side="left")
                tk.Label(row, text=note, font=F_BODY, bg=BG, fg=MUTED, justify="left",
                         wraplength=self.wrap - 40, anchor="w").pack(side="left", fill="x")

        tk.Label(body, text="Potrzebne biblioteki: " + ", ".join(dev.libs),
                 font=F_BODY, bg=BG, fg=MUTED, wraplength=self.wrap, justify="left"
                 ).pack(anchor="w", padx=18, pady=(10, 0))

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", padx=18, pady=(14, 4))
        self.test_button = self._button(actions, "Testuj ten czujnik", self.run_current, ACCENT)
        self.test_button.pack(side="left")
        if dev.live:
            ttk.Checkbutton(actions, text="test ciągły (co 2 s)", variable=self.live_var,
                            command=self._toggle_live).pack(side="left", padx=12)
        if dev.confirm:
            tk.Label(actions, text="test wykonuje fizyczną akcję — poprosi o potwierdzenie",
                     font=F_BODY, bg=BG, fg=STATUS_COLOR[T.WARN]).pack(side="left", padx=8)

        self.result_frame = tk.Frame(body, bg=BG)
        self.result_frame.pack(fill="x", padx=18, pady=(6, 24))
        self._render_result()

    def _section(self, parent, title: str):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(wrap, text=title, font=F_H2, bg=BG, fg=MUTED).pack(anchor="w")
        tk.Frame(wrap, bg=LINE, height=1).pack(fill="x", pady=(4, 0))

    def _table_row(self, table, row: int, a: str, b: str, c: str, header=False, color=FG):
        bg = PANEL if header else CARD
        width = max(self.wrap - 36, 240)
        cells = (
            (a, F_H2 if header else F_BODY, MUTED if header else FG, int(width * 0.28)),
            (b, F_H2 if header else F_MONO, MUTED if header else color, int(width * 0.30)),
            (c, F_BODY, MUTED, int(width * 0.36)),
        )
        for col, (text, font, fg, wrap) in enumerate(cells):
            tk.Label(table, text=text, font=font, bg=bg, fg=fg, anchor="w",
                     justify="left", wraplength=wrap).grid(
                row=row, column=col, sticky="nsew", padx=(10 if col == 0 else 4, 4),
                pady=(0, 1), ipady=4)

    def _render_result(self):
        for child in self.result_frame.winfo_children():
            child.destroy()
        dev = self.current
        if dev is None:
            return
        res = self.results.get(dev.id)
        if res is None:
            tk.Label(self.result_frame, text="Test jeszcze nie był uruchamiany.",
                     font=F_BODY, bg=BG, fg=MUTED).pack(anchor="w", pady=6)
            return

        color = STATUS_COLOR[res.status]
        card = tk.Frame(self.result_frame, bg=CARD, highlightbackground=color,
                        highlightthickness=1)
        card.pack(fill="x", pady=6)
        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(top, text=STATUS_TEXT[res.status], font=F_H1, bg=CARD,
                 fg=color).pack(side="left")
        tk.Label(top, text=datetime.datetime.now().strftime("%H:%M:%S"), font=F_BODY,
                 bg=CARD, fg=MUTED).pack(side="right")
        tk.Label(card, text=res.message, font=F_BODY, bg=CARD, fg=FG, justify="left",
                 wraplength=self.wrap - 20).pack(anchor="w", padx=12, pady=(0, 8))

        if res.values:
            grid = tk.Frame(card, bg=CARD)
            grid.pack(fill="x", padx=12, pady=(0, 8))
            for key, val in res.values.items():
                row = tk.Frame(grid, bg=CARD)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=key, font=F_BODY, bg=CARD, fg=MUTED, width=22,
                         anchor="nw").pack(side="left")
                tk.Label(row, text=str(val), font=F_MONO, bg=CARD, fg=FG, anchor="w",
                         justify="left", wraplength=max(self.wrap - 190, 200)
                         ).pack(side="left", fill="x")

        if res.hints:
            hint_box = tk.Frame(card, bg=PANEL)
            hint_box.pack(fill="x", padx=12, pady=(0, 12))
            tk.Label(hint_box, text="CO SPRAWDZIĆ", font=F_H2, bg=PANEL,
                     fg=MUTED).pack(anchor="w", padx=10, pady=(8, 2))
            for hint in res.hints:
                tk.Label(hint_box, text="– " + hint, font=F_BODY, bg=PANEL, fg=FG,
                         justify="left", wraplength=self.wrap - 30, anchor="w").pack(
                    anchor="w", padx=10, pady=1)
            tk.Frame(hint_box, bg=PANEL, height=6).pack()

    def _on_details_resize(self, event):
        """Zawijanie tekstu dopasowane do szerokości okna."""
        new = max(280, event.width - 70)
        if abs(new - self.wrap) > 30:
            self.wrap = new
            self._render_details()

    # ── rysunek złącza ───────────────────────────────────────────────────────
    def _draw_header_pins(self):
        canvas = self.pin_canvas
        canvas.delete("all")
        used: dict[int, tuple[str, str]] = {}
        if self.current:
            for wire in self.current.wiring:
                for pin in wire.pins:
                    if pin:
                        used[pin] = (wire.kind, wire.signal)

        height = canvas.winfo_height() or 470
        step = max(14, min(24, (height - 34) // 20))
        r = 8 if step >= 20 else max(5, step // 2 - 1)
        top = 14 + r
        cx_l, cx_r = 150, 186
        canvas.create_rectangle(cx_l - 22, top - r - 4, cx_r + 22, top + 19 * step + r + 4,
                                outline=LINE, width=1)
        for i in range(20):
            y = top + i * step
            for pin, cx, anchor, tx in ((2 * i + 1, cx_l, "e", cx_l - 14),
                                        (2 * i + 2, cx_r, "w", cx_r + 14)):
                _, name, bcm, kind, _alt = pinout.BY_PIN[pin]
                hit = used.get(pin)
                if hit:
                    fill = KIND_COLOR.get(hit[0], ACCENT)
                    outline, text_fg = "#ffffff", FG
                    label = f"{name} ← {hit[1]}" if anchor == "e" else f"{name} → {hit[1]}"
                    label = label if len(label) < 30 else label[:29] + "…"
                else:
                    fill = {"3v3": "#3a3020", "5v": "#3a2422", "gnd": "#26303c"}.get(
                        kind, "#1d2a3a")
                    outline, text_fg = LINE, "#63768c"
                    label = name
                canvas.create_oval(cx - r, y - r, cx + r, y + r, fill=fill, outline=outline)
                canvas.create_text(cx, y, text=str(pin), font=F_PIN,
                                   fill="#0b1017" if hit else "#8fa3ba")
                canvas.create_text(tx, y, text=label, font=F_PIN, fill=text_fg, anchor=anchor)

        if self.current and not used:
            canvas.create_text(168, top + 19 * step + r + 20, width=300,
                               text="ten element nie korzysta ze złącza GPIO "
                                    "(USB / CSI / osobne przewody)",
                               font=F_BODY, fill=MUTED, justify="center")

    # ── uruchamianie testów ──────────────────────────────────────────────────
    def run_current(self):
        dev = self.current
        if dev is None or self.busy:
            return
        if dev.confirm and not messagebox.askyesno("Potwierdzenie", dev.confirm, icon="warning"):
            self._set_status("Test anulowany.")
            return
        self._start([dev])

    def run_all(self):
        if self.busy:
            return
        safe = [d for d in self.devices if not d.confirm]
        skipped = [d.name for d in self.devices if d.confirm]
        self._stop_live()
        self.live_var.set(False)
        self._start(safe)
        if skipped:
            self._set_status(f"Testuję {len(safe)} elementów. Pominięte (wymagają "
                             f"potwierdzenia): {', '.join(skipped)}")

    def _start(self, devices: list[catalog.Device], live: bool = False):
        self.busy = True
        try:
            self.test_button.config(state="disabled", text="Trwa test…")
        except (AttributeError, tk.TclError):
            pass
        if not live:
            self._set_status(f"Testuję: {devices[0].name}…" if len(devices) == 1
                             else f"Testuję {len(devices)} elementów…")
        threading.Thread(target=self._worker, args=(devices, live), daemon=True).start()

    def _worker(self, devices: list[catalog.Device], live: bool):
        for dev in devices:
            if not live:
                self.queue.put(("progress", dev.id, None))
            try:
                result = dev.test()
            except Exception as exc:                      # test nigdy nie ubija GUI
                result = T.Result(T.FAIL, f"Nieobsłużony błąd testu: {exc!r}")
            self.queue.put(("result", dev.id, result))
        self.queue.put(("done", None, live))

    def _poll_queue(self):
        try:
            while True:
                kind, device_id, payload = self.queue.get_nowait()
                if kind == "progress":
                    self._set_status(f"Testuję: {catalog.BY_ID[device_id].name}…")
                elif kind == "result":
                    self.results[device_id] = payload
                    self._refresh_tree_item(device_id)
                    if self.current and self.current.id == device_id:
                        self._render_details()
                elif kind == "done":
                    self.busy = False
                    try:
                        self.test_button.config(state="normal", text="Testuj ten czujnik")
                    except (AttributeError, tk.TclError):
                        pass
                    if not payload:
                        self._set_status("Gotowe.")
                    if self.live_var.get() and self.current and self.current.live:
                        self.live_job = self.root.after(LIVE_INTERVAL_MS, self._live_tick)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _toggle_live(self):
        if self.live_var.get():
            self._set_status("Test ciągły włączony — odczyt co 2 s.")
            self._live_tick()
        else:
            self._stop_live()
            self._set_status("Test ciągły wyłączony.")

    def _live_tick(self):
        self.live_job = None
        if not self.live_var.get() or self.busy or self.current is None:
            return
        if self.current.confirm or not self.current.live:
            self.live_var.set(False)
            return
        self._start([self.current], live=True)

    def _stop_live(self):
        if self.live_job is not None:
            try:
                self.root.after_cancel(self.live_job)
            except tk.TclError:
                pass
            self.live_job = None
        self.live_var.set(False)

    # ── pozostałe akcje ──────────────────────────────────────────────────────
    def _toggle_sim(self):
        T.set_simulation(self.sim_var.get())
        self._set_status("Tryb symulacji WŁĄCZONY — wartości są zmyślone."
                         if self.sim_var.get() else
                         "Tryb symulacji wyłączony — testy idą do prawdziwego sprzętu.")

    def save_report(self):
        if not self.results:
            messagebox.showinfo("Raport", "Najpierw uruchom choć jeden test.")
            return
        stamp = datetime.datetime.now()
        path = REPO_ROOT / "testy" / f"raport-{stamp:%Y-%m-%d_%H%M}.txt"
        lines = [
            "StratoSTEAM — raport testu sprzętu",
            f"Data: {stamp:%Y-%m-%d %H:%M:%S}",
            f"Płytka: {pi_model() or 'brak Raspberry Pi'}",
            f"Tryb symulacji: {'TAK' if self.sim_var.get() else 'nie'}",
            "=" * 72, "",
        ]
        for dev in self.devices:
            res = self.results.get(dev.id)
            if res is None:
                continue
            lines.append(f"[{STATUS_TEXT[res.status]}] {dev.name}  ({dev.group})")
            lines.append(f"    {res.message}")
            for key, val in res.values.items():
                lines.append(f"    {key}: {val}")
            for hint in res.hints:
                lines.append(f"    → {hint}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        self._set_status(f"Raport zapisany: {path}")
        messagebox.showinfo("Raport", f"Zapisano:\n{path}")

    def _set_status(self, text: str):
        self.status_label.config(text=text)


def run(simulate: bool = False) -> None:
    root = tk.Tk()
    app = TesterApp(root, simulate=simulate)
    root.bind("<F5>", lambda e: app.run_current())
    root.mainloop()
