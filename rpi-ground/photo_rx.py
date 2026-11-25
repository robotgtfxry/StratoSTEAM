"""
Odbiór zdjęć nadawanych seriami (esp32/src/main.cpp, sendImgRound).

S3 zapowiada serię na zwykłym SF:  {"t":"ph","id","len","n","crc","sf","m"}
potem nadaje m pakietów binarnych na podanym SF:  0xA5, id, numer, liczba, dane
i wraca na zwykły SF. Braki ziemia zamawia komendą img_req, komplet potwierdza img_ok.
Zdjęcie pokazujemy dopiero, gdy jest całe i zgadza się CRC.
"""
import logging
import time
import zlib

log = logging.getLogger(__name__)

PKT_MAGIC = 0xA5
HEADER = 4
DATA = 240
MAX_PKTS = 128
MAX_REQ = 12            # tyle razy zamawiamy braki, potem odpuszczamy zdjęcie
IDLE_S = 6              # tyle ciszy po serii, zanim zamówimy braki


def airtime(sf: int, size: int, bw: float = 125e3) -> float:
    """Czas nadawania pakietu LoRa [s] (CR 4/5, CRC, jawny nagłówek)."""
    ts = 2 ** sf / bw
    ldro = 2 if ts > 0.016 else 0
    n = 8 * size - 4 * sf + 44
    blocks = -(-n // (4 * (sf - ldro)))
    return (20.25 + max(blocks * 5, 0)) * ts


def choose_sf(snr: float | None) -> int:
    """Im lepszy sygnał, tym szybsza seria (i większe zdjęcie). Zapas ok. 9 dB do granicy SF."""
    if snr is None:
        return 10
    if snr > 2:
        return 7
    if snr > -1:
        return 8
    if snr > -4:
        return 9
    return 10


class PhotoRx:
    def __init__(self):
        self.id: int | None = None
        self.n = self.len = self.crc = 0
        self.parts: dict[int, bytes] = {}
        self.done_id: int | None = None      # ostatnio odebrane w całości
        self.last_rx = 0.0
        self.reqs = 0
        self.started = 0.0
        self._ack: int | None = None

    # ── zapowiedź / beacon ────────────────────────────────────────────────────

    def _begin(self, img_id: int, n: int, length: int, crc: int) -> bool:
        if not (0 < n <= MAX_PKTS and 0 < length <= n * DATA and 0 <= img_id <= 255):
            return False
        if (img_id, n, length, crc) == (self.id, self.n, self.len, self.crc):
            return True
        self.id, self.n, self.len, self.crc = img_id, n, length, crc
        self.parts, self.reqs = {}, 0
        self.started = self.last_rx = time.time()
        return True

    def announce(self, p: dict) -> tuple[int, int] | None:
        """Zapowiedź serii → (SF, liczba pakietów) albo None, gdy bez sensu."""
        try:
            if not self._begin(int(p["id"]), int(p["n"]), int(p["len"]), int(p["crc"])):
                return None
            sf, m = int(p["sf"]), int(p["m"])
        except (KeyError, TypeError, ValueError):
            return None
        self.last_rx = time.time()
        return (sf, m) if 7 <= sf <= 12 and 0 < m <= MAX_PKTS else None

    def from_beacon(self, q) -> None:
        """Pole q beacona: zdjęcie czeka, nawet jeśli zgubiliśmy zapowiedź."""
        try:
            img_id, n, length, crc = (int(v) for v in q)
        except (TypeError, ValueError):
            return
        if self.done_id == img_id and self._same(img_id, n, length, crc):
            self._ack = img_id              # S3 nie usłyszał potwierdzenia
        else:
            self._begin(img_id, n, length, crc)

    def _same(self, *key) -> bool:
        return key == (self.id, self.n, self.len, self.crc)

    # ── pakiety serii ─────────────────────────────────────────────────────────

    def data(self, raw: bytes) -> int | None:
        """Pakiet binarny → jego numer albo None, gdy nie z tego zdjęcia."""
        if len(raw) <= HEADER or raw[0] != PKT_MAGIC or raw[1] != self.id or raw[3] != self.n:
            return None
        seq, body = raw[2], raw[HEADER:]
        want = min(DATA, self.len - seq * DATA)
        if seq >= self.n or len(body) != want:
            return None
        self.parts[seq] = body
        self.last_rx = time.time()
        return seq

    @property
    def receiving(self) -> bool:
        return self.id is not None and self.id != self.done_id and self.reqs <= MAX_REQ

    def complete(self) -> bytes | None:
        """Całe zdjęcie, jeśli jest komplet i zgadza się CRC (jednorazowo)."""
        if self.id is None or self.id == self.done_id or len(self.parts) < self.n:
            return None
        blob = b"".join(self.parts[i] for i in range(self.n))
        if zlib.crc32(blob) != self.crc:
            log.warning("Zdjęcie id=%d: zły CRC — odbieram od nowa", self.id)
            self.parts = {}
            return None
        self.done_id = self._ack = self.id
        return blob

    # ── co odpowiedzieć balonowi ──────────────────────────────────────────────

    def command(self, sf: int) -> dict | None:
        """Komenda do wysłania w oknie po beaconie."""
        if self._ack is not None:
            img_id, self._ack = self._ack, None
            return {"cmd": "img_ok", "id": img_id}
        if self.receiving and time.time() - self.last_rx > IDLE_S:
            self.reqs += 1
            if self.reqs > MAX_REQ:
                log.warning("Zdjęcie id=%d: rezygnuję (%d/%d)", self.id, len(self.parts), self.n)
                return {"cmd": "img_ok", "id": self.id}     # niech S3 przestanie je trzymać
            self.last_rx = time.time()
            bits = bytearray((self.n + 7) // 8)
            for i in range(self.n):
                if i not in self.parts:
                    bits[i // 8] |= 1 << (i % 8)
            return {"cmd": "img_req", "id": self.id, "sf": sf, "m": bits.hex()}
        return None

    def state(self) -> dict | None:
        if self.id is None:
            return None
        return {"id": self.id, "got": len(self.parts), "total": self.n, "bytes": self.len,
                "done": self.id == self.done_id, "failed": self.reqs > MAX_REQ,
                "ts": self.last_rx, "started": self.started}
