import io
import logging

import mss
from PIL import Image

log = logging.getLogger(__name__)


def _active_monitor(sct) -> dict:
    """Return the mss monitor dict for the screen containing the active window."""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        cx = (left + right) // 2
        cy = (top + bottom) // 2
        for mon in sct.monitors[1:]:  # [0] is the combined virtual canvas
            if (mon["left"] <= cx < mon["left"] + mon["width"] and
                    mon["top"] <= cy < mon["top"] + mon["height"]):
                log.debug("Active monitor: index %d (%dx%d @ %d,%d)",
                          sct.monitors.index(mon), mon["width"], mon["height"],
                          mon["left"], mon["top"])
                return mon
    except Exception as e:
        log.debug("Could not determine active monitor (%s), falling back to primary", e)
    return sct.monitors[1]


def capture_now(
    resize: tuple[int, int] = (1280, 720),
    quality: int = 75,
    monitor: int = -1,
) -> bytes:
    """
    Capture a screenshot and return JPEG bytes.

    monitor: -1 = active window's monitor (default)
              0 = all monitors combined
             1+ = specific monitor by mss index
    """
    with mss.MSS() as sct:
        if monitor == -1:
            mon = _active_monitor(sct)
        elif monitor == 0:
            mon = sct.monitors[0]
        else:
            idx = max(1, min(monitor, len(sct.monitors) - 1))
            mon = sct.monitors[idx]

        raw = sct.grab(mon)
        img = Image.frombytes("RGBA", (raw.width, raw.height), bytes(raw.bgra))

    img = img.convert("RGB").resize(resize, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    log.debug("Screenshot: %dx%d → %dx%d JPEG Q%d (%d KB)",
              raw.width, raw.height, resize[0], resize[1], quality, buf.tell() // 1024)
    return buf.getvalue()
