import json
import logging
import time
from pathlib import Path

from actions import keyboard

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


async def dispatch(tool_name: str, tool_input: dict) -> str:
    result: str
    try:
        if tool_name == "type_text":
            result = await keyboard.type_text(tool_input["text"])
        elif tool_name == "press_key":
            result = await keyboard.press_key(tool_input["key"])
        else:
            result = f"Unknown tool: {tool_name}"
            log.warning("Unknown tool requested: %s", tool_name)
    except Exception as e:
        result = f"Tool error ({tool_name}): {e}"
        log.exception("Tool %s failed with input %s", tool_name, tool_input)

    _log_call(tool_name, tool_input, result)
    return result
