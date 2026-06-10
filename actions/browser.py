"""
Singleton Playwright browser session.
One browser window, one page — reused across all tool calls within a session.
The browser window is visible (headless=False) so the user can see what's happening.
"""
import asyncio
import logging
import re

log = logging.getLogger(__name__)

_playwright = None
_browser = None
_page = None
_lock = asyncio.Lock()


async def _get_page():
    global _playwright, _browser, _page
    if _page is not None:
        try:
            # Verify the page is still alive
            await _page.title()
            return _page
        except Exception:
            _page = None

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is not installed. "
            "Run: pip install playwright && playwright install chromium"
        )

    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None or not _browser.is_connected():
        _browser = await _playwright.chromium.launch(headless=False)

    _page = await _browser.new_page()
    log.info("Browser session started")
    return _page


async def navigate(url: str) -> str:
    async with _lock:
        page = await _get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        except Exception as e:
            return f"Navigation failed: {e}"
        title = await page.title()
        log.info("Navigated to %s — %r", url, title)
        return f"Navigated to {url!r}. Page title: {title!r}"


async def click(selector: str = "", text: str = "") -> str:
    async with _lock:
        page = await _get_page()
        try:
            if text:
                locator = page.get_by_text(text, exact=False).first
                await locator.click(timeout=5_000)
                log.info("Clicked element with text %r", text)
                return f"Clicked element containing text {text!r}"
            if selector:
                await page.click(selector, timeout=5_000)
                log.info("Clicked selector %r", selector)
                return f"Clicked {selector!r}"
            return "Error: provide either selector or text"
        except Exception as e:
            return f"Click failed: {e}"


async def get_text(max_chars: int = 4_000) -> str:
    async with _lock:
        page = await _get_page()
        try:
            title = await page.title()
            url = page.url
            body = await page.inner_text("body")
            body = re.sub(r"\n{3,}", "\n\n", body).strip()
            if len(body) > max_chars:
                body = body[:max_chars] + f"\n…[truncated, {len(body) - max_chars} more chars]"
            log.info("Page text retrieved (%d chars)", len(body))
            return f"[{title}] ({url})\n\n{body}"
        except Exception as e:
            return f"get_text failed: {e}"


async def fill(selector: str, value: str) -> str:
    async with _lock:
        page = await _get_page()
        try:
            await page.fill(selector, value, timeout=5_000)
            log.info("Filled %r with %r", selector, value[:40])
            return f"Filled {selector!r} with {value!r}"
        except Exception as e:
            return f"Fill failed: {e}"


async def close() -> str:
    global _playwright, _browser, _page
    async with _lock:
        if _browser is not None:
            await _browser.close()
            _browser = None
            _page = None
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
        log.info("Browser session closed")
        return "Browser closed."
