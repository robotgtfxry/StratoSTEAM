"""
RTL-SDR odbiornik HF na balonie.
Mierzy siłę sygnału (dBFS) nadajnika naziemnego w zadanej częstotliwości.

Offset tuning: strojenie 100 kHz poniżej celu eliminuje szpilkę DC
z ADC RTL-SDR, która zaśmieciłaby pomiar nośnej.
"""
import logging
import threading

log = logging.getLogger(__name__)

_OFFSET_HZ   = 100_000   # przestrojenie poniżej celu
_UNAVAILABLE = -999.0    # wartość gdy brak SDR / błąd pomiaru

try:
    import numpy as np
    from rtlsdr import RtlSdr as _RtlSdr
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False
    log.warning("pyrtlsdr / numpy nie zainstalowane — SDR wyłączony")


class SdrReceiver:
    """
    Mierzy siłę sygnału CW nadajnika naziemnego.

    Parametry:
        target_freq_hz   – częstotliwość nadajnika (np. 7_100_000)
        sample_rate      – przepustowość SDR w Hz (250_000 zalecane)
        gain             – wzmocnienie: 'auto' lub liczba dB
        freq_correction  – korekcja PPM kwarcu dongla (zwykle 0–60)
        num_samples      – próbki na pomiar (256*1024 ≈ 1 s przy 250 kHz)
        bin_window       – ±bin wokół nośnej do uśredniania mocy
    """

    def __init__(
        self,
        target_freq_hz: int,
        sample_rate: int   = 250_000,
        gain                = "auto",
        freq_correction: int = 0,
        num_samples: int   = 256 * 1024,
        bin_window: int    = 15,
    ):
        self._target   = target_freq_hz
        self._sr       = sample_rate
        self._gain     = gain
        self._corr     = freq_correction
        self._n        = num_samples
        self._window   = bin_window
        self._lock     = threading.Lock()
        self._sdr      = None
        self._last_dbfs = _UNAVAILABLE

        if not _AVAILABLE:
            return

        try:
            sdr = _RtlSdr()
            sdr.sample_rate    = sample_rate
            sdr.center_freq    = target_freq_hz - _OFFSET_HZ
            sdr.freq_correction = freq_correction
            sdr.gain           = gain
            self._sdr = sdr
            log.info(
                "RTL-SDR gotowy: cel=%.3f MHz, strojenie=%.3f MHz, SR=%d kHz",
                target_freq_hz / 1e6,
                (target_freq_hz - _OFFSET_HZ) / 1e6,
                sample_rate // 1000,
            )
        except Exception as exc:
            log.error("RTL-SDR init error: %s", exc)

    @property
    def available(self) -> bool:
        return self._sdr is not None

    @property
    def last_dbfs(self) -> float:
        return self._last_dbfs

    def measure(self) -> float:
        """
        Dokonaj pomiaru mocy nośnej. Zwraca dBFS (ujemna wartość bliska 0 = silny sygnał).
        Zwraca -999.0 gdy brak SDR lub błąd.
        Wywołanie blokuje wątek na czas odczytu (~1–2 s przy 256k próbek).
        """
        if not self._sdr:
            return _UNAVAILABLE

        with self._lock:
            try:
                samples = self._sdr.read_samples(self._n)

                # Okno Blackmana tłumi przecieki widmowe
                window  = np.blackman(len(samples))
                samples = samples * window

                fft     = np.fft.fftshift(np.fft.fft(samples))
                psd     = (np.abs(fft) ** 2) / len(fft)

                # Bin odpowiadający offsetowi od centrum (+100 kHz)
                # center_freq = target - OFFSET, więc target jest na binie:
                # bin_offset = round(n * OFFSET / sample_rate)
                n       = len(psd)
                center  = n // 2
                bin_off = round(n * _OFFSET_HZ / self._sr)
                c_bin   = center + bin_off   # bin nośnej

                lo = max(0, c_bin - self._window)
                hi = min(n, c_bin + self._window + 1)

                signal_power = float(np.mean(psd[lo:hi]))
                dbfs = 10.0 * np.log10(max(signal_power, 1e-30))

                self._last_dbfs = round(dbfs, 1)
                log.debug("SDR pomiar: %.1f dBFS (bin=%d)", self._last_dbfs, c_bin)
                return self._last_dbfs

            except Exception as exc:
                log.warning("SDR pomiar nieudany: %s", exc)
                return _UNAVAILABLE

    def close(self) -> None:
        if self._sdr:
            try:
                self._sdr.close()
            except Exception:
                pass
            self._sdr = None
        log.info("RTL-SDR zamknięty")
