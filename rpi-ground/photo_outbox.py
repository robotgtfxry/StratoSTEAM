"""
Kolejka zdjęć do serwera. Pliki leżą w LOG_DIR/do-wyslania i znikają dopiero po przyjęciu
przez serwer, więc zdjęcia z lotu bez internetu dotrą po jego powrocie — także po restarcie.
"""
import base64
import logging
import os
import shutil
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY, OFFLINE_FLUSH_INTERVAL_S

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class PhotoOutbox:
    def __init__(self, directory: str):
        self._dir = directory

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, path: str) -> None:
        dst = os.path.join(self._dir, os.path.basename(path))
        try:
            os.makedirs(self._dir, exist_ok=True)
            try:
                os.link(path, dst)              # bez kopiowania; oryginał zostaje w dzienniku
            except FileExistsError:
                pass
            except OSError:
                shutil.copy2(path, dst)
        except OSError as e:
            log.warning("Zdjęcie nie trafiło do kolejki: %s", e)

    def waiting(self) -> list[str]:
        try:
            names = [n for n in os.listdir(self._dir) if n.endswith(".webp")]
        except OSError:
            return []
        return [os.path.join(self._dir, n) for n in sorted(names)]

    def flush(self) -> bool:
        """Wyślij po kolei, od najstarszego. False = serwer nie przyjął, spróbuj później."""
        for path in self.waiting():
            try:
                ts = os.path.getmtime(path)
                with open(path, "rb") as f:
                    blob = f.read()
                r = requests.post(f"{BACKEND_URL}/api/camera/chunk", headers=_HEADERS, timeout=15, json={
                    "type": "img", "id": int(ts) % 1_000_000, "seq": 0, "tot": 1, "ts": ts,
                    "data": base64.b64encode(blob).decode()})
                if r.status_code in (400, 422):
                    log.error("Zdjęcie %s odrzucone na stałe: %s", path, r.text[:200])
                elif r.status_code != 200:
                    log.warning("Zdjęcie: serwer odpowiedział %d", r.status_code)
                    return False
                os.remove(path)
                log.info("Zdjęcie wysłane na serwer: %s", os.path.basename(path))
            except (requests.RequestException, OSError) as e:
                log.debug("Zdjęcie czeka: %s", e)
                return False
        return True

    def _run(self) -> None:
        while True:
            try:
                ok = self.flush()
            except Exception:
                log.exception("Kolejka zdjęć")
                ok = False
            time.sleep(2 if ok else OFFLINE_FLUSH_INTERVAL_S)
