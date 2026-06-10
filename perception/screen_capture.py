import io
import logging

import mss
from PIL import Image

log = logging.getLogger(__name__)


def capture_now(resize: tuple[int, int] = (1280, 720), quality: int = 75) -> bytes:
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        raw = sct.grab(monitor)
        img = Image.frombytes("RGBA", (raw.width, raw.height), bytes(raw.bgra))

    img = img.convert("RGB").resize(resize, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    size_kb = buf.tell() // 1024
    log.debug("Screenshot: %dx%d JPEG Q%d (%d KB)", resize[0], resize[1], quality, size_kb)
    return buf.getvalue()
