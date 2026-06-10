import asyncio
import logging
from typing import Callable, Awaitable

import ollama
from ai.tools import TOOLS

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, settings):
        self._model = settings.ollama_model
        self._max_tool_calls = settings.max_tool_calls_per_turn
        self._client = ollama.Client(host=settings.ollama_host)

    async def complete(
        self,
        messages: list[dict],
        system: str,
        on_tool_call: Callable[[str, dict], Awaitable[str]],
    ) -> str:
        full_messages = [{"role": "system", "content": system}] + messages
        tool_call_count = 0

        while tool_call_count < self._max_tool_calls:
            response = await asyncio.to_thread(
                self._client.chat,
                model=self._model,
                messages=full_messages,
                tools=TOOLS,
            )

            msg = response.message
            log.debug("Stop: tool_calls=%s", bool(msg.tool_calls))

            if not msg.tool_calls:
                return (msg.content or "").strip()

            # Append assistant turn with tool calls
            full_messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in msg.tool_calls
                ],
            })

            # Execute each tool and append results
            for tc in msg.tool_calls:
                name = tc.function.name
                args = tc.function.arguments  # already a dict
                log.info("Tool: %s %s", name, args)
                try:
                    result = await on_tool_call(name, args)
                except Exception as e:
                    result = f"Error executing {name}: {e}"
                    log.exception("Tool %s raised", name)

                full_messages.append({
                    "role": "tool",
                    "content": str(result),
                })
                tool_call_count += 1

        return "I've reached the action limit for this request."

    async def complete_simple(self, messages: list[dict], system: str) -> str:
        """Single-shot completion with no tools — used for fact extraction."""
        full_messages = [{"role": "system", "content": system}] + messages
        response = await asyncio.to_thread(
            self._client.chat,
            model=self._model,
            messages=full_messages,
        )
        return (response.message.content or "").strip()
