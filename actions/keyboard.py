import asyncio
import logging

import pyautogui

log = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Virtual-key map for background injection via PostMessage
_VK: dict[str, int] = {
    "enter": 0x0D, "return": 0x0D, "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "tab": 0x09, "backspace": 0x08,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D, "delete": 0x2E,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _VK[_c] = ord(_c.upper())
for _d in "0123456789":
    _VK[_d] = ord(_d)

_MODIFIERS: dict[str, int] = {
    "ctrl": 0x11, "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "win": 0x5B,
}


def _type_text(text: str):
    pyautogui.write(text, interval=0.02)


def _press_key(key: str):
    parts = [p.strip() for p in key.lower().split("+")]
    pyautogui.hotkey(*parts)


def _find_hwnd(process_name: str) -> int | None:
    try:
        import win32gui
        import win32process
        import psutil
    except ImportError:
        raise RuntimeError("pywin32 and psutil are required for send_keys_to_window")

    name_lower = process_name.lower()
    if not name_lower.endswith(".exe"):
        name_lower += ".exe"

    matches: list[int] = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name().lower()
            if proc_name == name_lower:
                matches.append(hwnd)
        except Exception:
            pass

    win32gui.EnumWindows(_cb, None)
    return matches[0] if matches else None


def _post_keys(hwnd: int, key: str):
    import win32api
    import win32con

    parts = [p.strip().lower() for p in key.split("+")]
    mod_vks = [_MODIFIERS[p] for p in parts if p in _MODIFIERS]
    key_vks = [_VK[p] for p in parts if p not in _MODIFIERS]

    if not key_vks:
        raise ValueError(f"No recognized key in: {key!r}")

    for vk in mod_vks:
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    for vk in key_vks:
        win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)
    for vk in reversed(mod_vks):
        win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)


def _send_keys_to_window(process_name: str, key: str):
    hwnd = _find_hwnd(process_name)
    if hwnd is None:
        raise RuntimeError(f"No visible window found for process: {process_name!r}")
    _post_keys(hwnd, key)
    log.info("send_keys_to_window: %r → %r (hwnd=%d)", key, process_name, hwnd)


async def type_text(text: str) -> str:
    log.debug("type_text: %r", text[:80])
    await asyncio.to_thread(_type_text, text)
    return f"Typed {len(text)} characters"


async def press_key(key: str) -> str:
    log.debug("press_key: %r", key)
    await asyncio.to_thread(_press_key, key)
    return f"Pressed: {key}"


async def send_keys_to_window(process_name: str, key: str) -> str:
    await asyncio.to_thread(_send_keys_to_window, process_name, key)
    return f"Sent {key!r} to {process_name}"
