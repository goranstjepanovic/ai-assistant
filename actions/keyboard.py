import asyncio
import logging

import pyautogui

log = logging.getLogger(__name__)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def _type_text(text: str):
    pyautogui.write(text, interval=0.02)


def _press_key(key: str):
    parts = [p.strip() for p in key.lower().split("+")]
    pyautogui.hotkey(*parts)


async def type_text(text: str) -> str:
    log.debug("type_text: %r", text[:80])
    await asyncio.to_thread(_type_text, text)
    return f"Typed {len(text)} characters"


async def press_key(key: str) -> str:
    log.debug("press_key: %r", key)
    await asyncio.to_thread(_press_key, key)
    return f"Pressed: {key}"
