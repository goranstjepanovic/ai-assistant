import asyncio
import logging

log = logging.getLogger(__name__)


def _read() -> str:
    import win32clipboard
    import win32con
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            return text if text else "(clipboard is empty)"
        return "(no text in clipboard)"
    finally:
        win32clipboard.CloseClipboard()


def _write(text: str):
    import win32clipboard
    import win32con
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


async def read_async() -> str:
    result = await asyncio.to_thread(_read)
    log.debug("read_clipboard: %d chars", len(result))
    return result


async def write_async(text: str) -> str:
    await asyncio.to_thread(_write, text)
    log.debug("write_clipboard: %d chars", len(text))
    return f"Copied {len(text)} characters to clipboard."
