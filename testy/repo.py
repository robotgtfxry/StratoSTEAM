"""
Dostęp do reszty repozytorium StratoSTEAM.

Tester nie kopiuje sterowników — ładuje TE SAME pliki, które lecą na balonie
(`rpi-air/sensors/*.py`, `rpi-air/hardware/*.py`) oraz konfiguracje
(`rpi-air/config.py`, `rpi-ground/config.py`). Dzięki temu test sprawdza
dokładnie ten kod, który potem działa w locie.

Moduły ładowane są po ścieżce, pod własnymi nazwami (np. "air_sensor_bme280"),
żeby nie przesłonić bibliotek z pip (plik sensors/bme280.py vs pakiet bme280).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

_CACHE: dict[str, Any] = {}


def load_repo_module(name: str, relpath: str):
    """Wczytaj moduł z repozytorium po ścieżce względnej. Rzuca ImportError/FileNotFoundError."""
    if name in _CACHE:
        return _CACHE[name]
    path = REPO_ROOT / relpath
    if not path.exists():
        raise FileNotFoundError(f"brak pliku {relpath} (szukano w {REPO_ROOT})")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"nie można wczytać {relpath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    _CACHE[name] = module
    return module


def _cfg(name: str, relpath: str, key: str, default):
    try:
        return getattr(load_repo_module(name, relpath), key, default)
    except Exception:
        return default


def air(key: str, default=None):
    """Wartość z rpi-air/config.py (węzeł balonowy)."""
    return _cfg("stratosteam_air_config", "rpi-air/config.py", key, default)


def ground(key: str, default=None):
    """Wartość z rpi-ground/config.py (stacja naziemna)."""
    return _cfg("stratosteam_ground_config", "rpi-ground/config.py", key, default)


def pi_model() -> str | None:
    """Model płytki z /proc/device-tree/model, np. 'Raspberry Pi 5 Model B Rev 1.0'."""
    try:
        with open("/proc/device-tree/model", "rb") as f:
            return f.read().decode("utf-8", "replace").strip("\x00 \n")
    except OSError:
        return None


def is_raspberry_pi() -> bool:
    model = pi_model()
    return bool(model and "Raspberry Pi" in model)


def is_pi5() -> bool:
    model = pi_model()
    return bool(model and "Raspberry Pi 5" in model)
