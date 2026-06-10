import asyncio
import json
import logging
import time
from pathlib import Path

from actions import keyboard
from actions import apps as apps_module
from actions import shell as shell_module
from actions import search as search_module

log = logging.getLogger(__name__)

_LOG_PATH = Path("logs/tool_calls.jsonl")


def _log_call(tool_name: str, tool_input: dict, result: str):
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.time(),
        "tool": tool_name,
        "input": tool_input,
        "result": result[:500],
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        log.warning("Failed to write tool log: %s", e)


class ActionRunner:
    def __init__(self, memory=None, settings=None):
        self._memory = memory
        self._settings = settings

    async def dispatch(self, tool_name: str, tool_input: dict) -> str:
        result: str
        try:
            result = await self._dispatch(tool_name, tool_input)
        except Exception as e:
            result = f"Tool error ({tool_name}): {e}"
            log.exception("Tool %s failed with input %s", tool_name, tool_input)

        _log_call(tool_name, tool_input, result)
        return result

    async def _dispatch(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "web_search":
            return await search_module.web_search_async(
                tool_input["query"],
                tool_input.get("max_results", 5),
            )

        if tool_name == "list_apps":
            return await apps_module.list_apps_async()

        if tool_name == "open_app":
            return await apps_module.open_app_async(tool_input["name"])

        if tool_name == "type_text":
            return await keyboard.type_text(tool_input["text"])

        if tool_name == "press_key":
            return await keyboard.press_key(tool_input["key"])

        if tool_name == "send_keys_to_window":
            return await keyboard.send_keys_to_window(
                tool_input["process_name"], tool_input["key"]
            )

        if tool_name == "run_shell":
            voice = self._settings.tts_voice if self._settings else "en-GB-SoniaNeural"
            engine = self._settings.tts_engine if self._settings else "edge-tts"
            return await shell_module.run_shell(
                tool_input["command"],
                tool_input.get("working_dir", "~"),
                voice=voice,
                engine=engine,
            )

        if tool_name == "open_url":
            return await _open_url(tool_input["url"])

        if tool_name == "browser_navigate":
            from actions import browser as _browser
            return await _browser.navigate(tool_input["url"])

        if tool_name == "browser_click":
            from actions import browser as _browser
            return await _browser.click(
                selector=tool_input.get("selector", ""),
                text=tool_input.get("text", ""),
            )

        if tool_name == "browser_get_text":
            from actions import browser as _browser
            return await _browser.get_text(tool_input.get("max_chars", 4000))

        if tool_name == "browser_fill":
            from actions import browser as _browser
            return await _browser.fill(tool_input["selector"], tool_input["value"])

        if tool_name == "browser_close":
            from actions import browser as _browser
            return await _browser.close()

        if tool_name == "read_clipboard":
            from actions import clipboard
            return await clipboard.read_async()

        if tool_name == "write_clipboard":
            from actions import clipboard
            return await clipboard.write_async(tool_input["text"])

        if tool_name == "enroll_voice":
            from actions import enroll as _enroll
            return await _enroll.enroll_speaker(tool_input["name"], self._settings)

        if tool_name == "remember_fact":
            if self._memory:
                await asyncio.to_thread(
                    self._memory.upsert_fact,
                    tool_input["key"],
                    tool_input["value"],
                    "ai_tool",
                )
                return f"Remembered: {tool_input['key']} = {tool_input['value']}"
            return "Memory not available."

        log.warning("Unknown tool requested: %s", tool_name)
        return f"Unknown tool: {tool_name}"


async def _open_url(url: str) -> str:
    import webbrowser
    await asyncio.to_thread(webbrowser.open, url)
    log.info("Opened URL: %s", url)
    return f"Opened {url}"


# Legacy top-level function kept for backwards compatibility
async def dispatch(tool_name: str, tool_input: dict) -> str:
    return await ActionRunner().dispatch(tool_name, tool_input)
