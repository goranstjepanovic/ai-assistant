import logging
import threading
import time

log = logging.getLogger(__name__)

_peak: float = 0.0
_threshold: float = 0.6
_lock = threading.Lock()
_started = False


def start(threshold: float = 0.6) -> None:
    global _threshold, _started
    if _started:
        return
    _threshold = threshold
    _started = True
    threading.Thread(target=_poll_loop, daemon=True, name="audio-monitor").start()
    log.info("System audio monitor started (threshold=%.0f%%)", threshold * 100)


def is_active() -> bool:
    """Return True if system output audio is above the suppression threshold."""
    with _lock:
        return _peak >= _threshold


def peak() -> float:
    with _lock:
        return _peak


def _poll_loop() -> None:
    global _peak
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        from comtypes import CLSCTX_ALL

        speakers = AudioUtilities.GetSpeakers()
        interface = speakers.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
        meter = interface.QueryInterface(IAudioMeterInformation)

        while True:
            try:
                val = float(meter.GetPeakValue())
                with _lock:
                    _peak = val
            except Exception:
                pass
            time.sleep(0.1)

    except Exception as e:
        log.warning("System audio monitor unavailable (%s) — suppression disabled", e)
