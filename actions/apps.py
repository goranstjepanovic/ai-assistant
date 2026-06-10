import asyncio
import difflib
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

_START_MENU_ROOTS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    Path("C:/ProgramData/Microsoft/Windows/Start Menu/Programs"),
]

_cache: dict[str, Path] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 300.0  # re-scan every 5 minutes


def _scan() -> dict[str, Path]:
    apps: dict[str, Path] = {}
    for root in _START_MENU_ROOTS:
        if not root.exists():
            continue
        for lnk in root.rglob("*.lnk"):
            name = lnk.stem
            apps[name.lower()] = lnk
    log.debug("Start Menu scan: %d shortcuts found", len(apps))
    return apps


def _get_apps() -> dict[str, Path]:
    global _cache, _cache_ts
    if not _cache or (time.monotonic() - _cache_ts) > _CACHE_TTL:
        _cache = _scan()
        _cache_ts = time.monotonic()
    return _cache


def list_apps() -> str:
    apps = _get_apps()
    names = sorted(lnk.stem for lnk in apps.values())
    if not names:
        return "No apps found in Start Menu."
    return "\n".join(names)


def open_app(name: str) -> str:
    apps = _get_apps()
    query = name.lower().strip()

    # Exact match first
    if query in apps:
        lnk = apps[query]
        os.startfile(str(lnk))
        log.info("Opened app (exact): %s", lnk.stem)
        return f"Opened {lnk.stem}."

    # Fuzzy match
    matches = difflib.get_close_matches(query, apps.keys(), n=1, cutoff=0.55)
    if matches:
        lnk = apps[matches[0]]
        os.startfile(str(lnk))
        log.info("Opened app (fuzzy '%s' → '%s'): %s", query, matches[0], lnk)
        return f"Opened {lnk.stem}."

    # Fallback: try os.startfile with the raw name (handles system apps like notepad, calc)
    try:
        os.startfile(name)
        log.info("Opened app (startfile fallback): %s", name)
        return f"Opened {name}."
    except OSError:
        pass

    return (
        f"Could not find an app matching '{name}'. "
        "Try calling list_apps to see available app names."
    )


async def list_apps_async() -> str:
    return await asyncio.to_thread(list_apps)


async def open_app_async(name: str) -> str:
    return await asyncio.to_thread(open_app, name)
