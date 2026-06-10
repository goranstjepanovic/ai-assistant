import io
import logging

from PIL import Image

log = logging.getLogger(__name__)

# dxcam is optional — faster DirectX capture, useful for exclusive-fullscreen games
_dxcam_camera = None
try:
    import dxcam as _dxcam
    _DXCAM_AVAILABLE = True
except ImportError:
    _DXCAM_AVAILABLE = False


def _get_dxcam():
    global _dxcam_camera
    if _dxcam_camera is None:
        _dxcam_camera = _dxcam.create(output_color="RGB")
    return _dxcam_camera


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
    import mss
    with mss.MSS() as sct2:
        return sct2.monitors[1]


def _capture_mss(resize: tuple[int, int], quality: int, monitor: int) -> bytes:
    import mss
    with mss.mss() as sct:
        if monitor == -1:
            mon = _active_monitor(sct)
        elif monitor == 0:
            mon = sct.monitors[0]
        else:
            idx = max(1, min(monitor, len(sct.monitors) - 1))
            mon = sct.monitors[idx]

        raw = sct.grab(mon)
        img = Image.frombytes("RGBA", (raw.width, raw.height), bytes(raw.bgra))

    log.debug("mss: %dx%d", raw.width, raw.height)
    img = img.convert("RGB").resize(resize, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _capture_dxcam(resize: tuple[int, int], quality: int) -> bytes:
    camera = _get_dxcam()
    frame = camera.grab()
    if frame is None:
        raise RuntimeError("dxcam returned None (no new frame) — falling back to mss")
    log.debug("dxcam: %dx%d", frame.shape[1], frame.shape[0])
    img = Image.fromarray(frame).resize(resize, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def capture_now(
    resize: tuple[int, int] = (1280, 720),
    quality: int = 75,
    monitor: int = -1,
    backend: str = "mss",
) -> bytes:
    """
    Capture a screenshot and return JPEG bytes.

    backend: "mss" (default) or "dxcam" (faster for exclusive-fullscreen games;
             requires `pip install dxcam`)
    monitor: -1 = active window's monitor, 0 = all combined, 1+ = specific index
             (ignored when backend="dxcam")
    """
    if backend == "dxcam":
        if not _DXCAM_AVAILABLE:
            log.warning("dxcam not installed — falling back to mss (pip install dxcam)")
        else:
            try:
                data = _capture_dxcam(resize, quality)
                log.debug("Screenshot via dxcam → %dx%d JPEG Q%d (%d KB)",
                          resize[0], resize[1], quality, len(data) // 1024)
                return data
            except Exception as e:
                log.warning("dxcam capture failed (%s) — falling back to mss", e)

    data = _capture_mss(resize, quality, monitor)
    log.debug("Screenshot via mss → %dx%d JPEG Q%d (%d KB)",
              resize[0], resize[1], quality, len(data) // 1024)
    return data
