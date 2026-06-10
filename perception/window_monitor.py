import asyncio
import json
import logging
from pathlib import Path

import psutil
from core.event_bus import EventBus, WindowChangeEvent

log = logging.getLogger(__name__)

try:
    import win32gui
    import win32process
    _WIN32 = True
except ImportError:
    _WIN32 = False
    log.warning("pywin32 not available — window monitoring disabled")

_GAME_PROCESSES: set[str] = set()
_GAME_PROCESSES_PATH = Path("config/game_processes.json")

IDE_PROCS = {"code.exe", "pycharm64.exe", "pycharm.exe", "rider64.exe", "rider.exe",
             "nvim.exe", "vim.exe", "sublime_text.exe", "cursor.exe"}
TERMINAL_PROCS = {"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
                  "alacritty.exe", "wezterm-gui.exe"}
MEDIA_PROCS = {"vlc.exe", "mpv.exe", "mpc-hc.exe", "mpc-hc64.exe", "spotify.exe"}
BROWSER_PROCS = {"chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe"}
COMM_PROCS = {"discord.exe", "slack.exe", "teams.exe", "zoom.exe"}
MEDIA_TITLES = {"youtube", "netflix", "twitch", "plex", "hulu", "disney+", "spotify"}


def _load_game_processes():
    global _GAME_PROCESSES
    if _GAME_PROCESSES_PATH.exists():
        with open(_GAME_PROCESSES_PATH) as f:
            _GAME_PROCESSES = {p.lower() for p in json.load(f)}


def _classify(process_name: str, window_title: str) -> str:
    p = process_name.lower()
    t = window_title.lower()
    if p in _GAME_PROCESSES:
        return "game"
    if p in MEDIA_PROCS or any(pat in t for pat in MEDIA_TITLES):
        return "media"
    if p in BROWSER_PROCS:
        return "browser"
    if p in IDE_PROCS:
        return "ide"
    if p in TERMINAL_PROCS:
        return "terminal"
    if p in COMM_PROCS:
        return "communication"
    return "unknown"


def _get_foreground_info() -> tuple[str, str]:
    if not _WIN32:
        return "unknown.exe", ""
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        return proc.name(), title
    except Exception:
        return "unknown.exe", ""


class WindowMonitor:
    def __init__(self, bus: EventBus, poll_interval_ms: int = 500):
        self._bus = bus
        self._interval = poll_interval_ms / 1000.0
        self._current: WindowChangeEvent | None = None
        _load_game_processes()

    @property
    def current(self) -> WindowChangeEvent | None:
        return self._current

    async def run(self):
        log.info("WindowMonitor started (poll every %dms)", int(self._interval * 1000))
        while True:
            process_name, window_title = await asyncio.to_thread(_get_foreground_info)
            app_class = _classify(process_name, window_title)
            new_event = WindowChangeEvent(process_name, window_title, app_class)

            if self._current is None or (
                self._current.process_name != process_name
                or self._current.window_title != window_title
            ):
                self._current = new_event
                await self._bus.publish("window_change", new_event)
                log.debug(
                    "Window: %s [%s] — %s",
                    process_name,
                    app_class,
                    window_title[:60],
                )

            await asyncio.sleep(self._interval)
