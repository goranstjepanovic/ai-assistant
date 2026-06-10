import asyncio
import logging
from typing import Callable, Awaitable

import anthropic
from ai.tools import TOOLS

log = logging.getLogger(__name__)


class ClaudeClient:
    def __init__(self, settings):
        self._client = anthropic.Anthropic(api_key=settings.api_key)
        self._model = settings.claude_model
        self._max_tokens = settings.claude_max_tokens
        self._max_tool_calls = settings.max_tool_calls_per_turn

    async def complete(
        self,
        messages: list[dict],
        system: str,
        on_tool_call: Callable[[str, dict], Awaitable[str]],
    ) -> str:
        tool_call_count = 0

        while tool_call_count < self._max_tool_calls:
            response = await asyncio.to_thread(
                self._client.messages.create,
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            log.debug("Stop reason: %s, tokens: %d", response.stop_reason, response.usage.output_tokens)

            if response.stop_reason != "tool_use":
                parts = [b.text for b in response.content if hasattr(b, "text")]
                return " ".join(parts).strip()

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    log.info("Tool: %s %s", block.name, block.input)
                    try:
                        result = await on_tool_call(block.name, block.input)
                    except Exception as e:
                        result = f"Error executing {block.name}: {e}"
                        log.exception("Tool %s raised", block.name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    })
                    tool_call_count += 1

            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ]

        return "I've reached the action limit for this request."
