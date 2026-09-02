#!/usr/bin/env python3
"""
StratoSTEAM — Tester czujników.

    python3 testy/main.py              # okno GUI (tkinter)
    python3 testy/main.py --sim        # GUI z danymi udawanymi (bez sprzętu)
    python3 testy/main.py --lista      # spis sprzętu w terminalu
    python3 testy/main.py --konsola    # wszystkie bezpieczne testy bez GUI (przez SSH)
    python3 testy/main.py --test bme280
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalog          # noqa: E402
import hw_tests as T    # noqa: E402
from repo import pi_model  # noqa: E402

MARK = {T.OK: "[ OK ]", T.WARN: "[UWAGA]", T.FAIL: "[BŁĄD]",
        T.MISSING: "[BRAK]", T.INFO: "[INFO]"}


def print_list() -> None:
    print(f"Płytka: {pi_model() or 'brak Raspberry Pi'}\n")
    for group in catalog.GROUPS:
        items = [d for d in catalog.DEVICES if d.group == group]
        if not items:
            continue
        print(f"── {group} " + "─" * max(0, 60 - len(group)))
        for dev in items:
            flag = "  (wymaga potwierdzenia)" if dev.confirm else ""
            print(f"  {dev.id:<15} {dev.name}{flag}")
            print(f"  {'':<15} {dev.bus}")
        print()


def print_result(dev: catalog.Device, res: T.Result) -> None:
    print(f"{MARK.get(res.status, '[????]')} {dev.name}")
    print(f"        {res.message}")
    for key, val in res.values.items():
        print(f"        {key}: {val}")
    for hint in res.hints:
        print(f"        → {hint}")
    print()


def run_console(only: str | None = None) -> int:
    if only:
        dev = catalog.BY_ID.get(only)
        if dev is None:
            print(f"Nie znam elementu '{only}'. Lista: python3 testy/main.py --lista")
            return 2
        devices = [dev]
    else:
        devices = [d for d in catalog.DEVICES if not d.confirm]
        print("Testy wykonujące fizyczne akcje (przekaźniki, nadajnik HF) są pomijane —\n"
              "uruchom je pojedynczo: python3 testy/main.py --test relays\n")

    print(f"Płytka: {pi_model() or 'brak Raspberry Pi'}\n")
    bad = 0
    for dev in devices:
        try:
            res = dev.test()
        except Exception as exc:
            res = T.Result(T.FAIL, f"Nieobsłużony błąd testu: {exc!r}")
        if res.status in (T.FAIL, T.WARN):
            bad += 1
        print_result(dev, res)
    print(f"Zakończono. Elementów do sprawdzenia: {bad}/{len(devices)}")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tester czujników StratoSTEAM — GUI mówi, jaki to czujnik "
                    "i jak go podłączyć do Raspberry Pi 5.")
    parser.add_argument("--sim", "--symulacja", action="store_true", dest="sim",
                        help="tryb symulacji — udawane odczyty, do nauki obsługi bez sprzętu")
    parser.add_argument("--lista", action="store_true", help="wypisz spis sprzętu i zakończ")
    parser.add_argument("--konsola", action="store_true",
                        help="uruchom testy w terminalu, bez okna (przydatne przez SSH)")
    parser.add_argument("--test", metavar="ID",
                        help="uruchom jeden test w terminalu, np. --test bme280")
    args = parser.parse_args()

    if args.sim:
        T.set_simulation(True)
    if args.lista:
        print_list()
        return 0
    if args.konsola or args.test:
        return run_console(args.test)

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Brak tkinter. Na Raspberry Pi OS zainstaluj:\n"
              "    sudo apt install python3-tk\n"
              "Albo uruchom bez okna:  python3 testy/main.py --konsola")
        return 2

    from gui import run
    run(simulate=args.sim)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
