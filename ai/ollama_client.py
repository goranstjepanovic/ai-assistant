import asyncio
import logging
import threading
from typing import Callable, Awaitable, AsyncGenerator

import ollama
from ai.tools import TOOLS

log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, settings):
        self._model = settings.ollama_model
        self._max_tool_calls = settings.max_tool_calls_per_turn
        self._client = ollama.Client(host=settings.ollama_host)
        self._inactivity_s = getattr(settings, "ollama_inactivity_timeout_s", 45.0)

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

    async def stream_complete(
        self,
        messages: list[dict],
        system: str,
        on_tool_call: Callable[[str, dict], Awaitable[str]],
    ) -> AsyncGenerator[str, None]:
        """
        Like complete(), but streams the final text response chunk by chunk.
        Tool-use turns run non-streaming (models output empty content when calling
        tools, so there's nothing useful to stream there anyway). Once all tools
        are done the final text turn is streamed via a thread→asyncio-queue bridge.
        """
        full_messages = [{"role": "system", "content": system}] + messages
        tool_call_count = 0

        while tool_call_count < self._max_tool_calls:
            # Stream this turn; collect content chunks AND any tool calls
            tool_calls_found: list = []
            accumulated: list[str] = []

            async for chunk in self._stream_turn(full_messages, tool_calls_found):
                accumulated.append(chunk)
                yield chunk

            if not tool_calls_found:
                return  # accumulated content was the final answer

            # Tool calls found (content is usually empty at this point)
            full_messages.append({
                "role": "assistant",
                "content": "".join(accumulated),
                "tool_calls": [
                    {
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in tool_calls_found
                ],
            })
            for tc in tool_calls_found:
                name = tc.function.name
                args = tc.function.arguments
                log.info("Tool: %s %s", name, args)
                try:
                    result = await on_tool_call(name, args)
                except Exception as e:
                    result = f"Error executing {name}: {e}"
                    log.exception("Tool %s raised", name)
                full_messages.append({"role": "tool", "content": str(result)})
                tool_call_count += 1

        yield "I've reached the action limit for this request."

    async def _stream_turn(
        self, messages: list[dict], tool_calls_out: list
    ) -> AsyncGenerator[str, None]:
        """
        Stream one conversation turn through a thread→queue bridge.
        Yields content chunks; appends any tool calls to tool_calls_out.
        Raises asyncio.TimeoutError if no chunk arrives within inactivity_s.
        """
        loop = asyncio.get_running_loop()
        chunk_q: asyncio.Queue = asyncio.Queue()

        def _run():
            try:
                for chunk in self._client.chat(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    stream=True,
                ):
                    loop.call_soon_threadsafe(chunk_q.put_nowait, chunk)
            except Exception as exc:
                loop.call_soon_threadsafe(chunk_q.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(chunk_q.put_nowait, None)

        threading.Thread(target=_run, daemon=True).start()

        while True:
            try:
                item = await asyncio.wait_for(chunk_q.get(), timeout=self._inactivity_s)
            except asyncio.TimeoutError:
                log.warning(
                    "Ollama produced no output for %.0fs — aborting stream",
                    self._inactivity_s,
                )
                raise
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            content = item.message.content or ""
            if content:
                yield content
            if item.message.tool_calls:
                tool_calls_out.extend(item.message.tool_calls)

    async def complete_simple(self, messages: list[dict], system: str) -> str:
        """Single-shot completion with no tools — used for fact extraction."""
        full_messages = [{"role": "system", "content": system}] + messages
        response = await asyncio.to_thread(
            self._client.chat,
            model=self._model,
            messages=full_messages,
        )
        return (response.message.content or "").strip()
