import asyncio
import logging
import time

from core.event_bus import EventBus, SpeechEvent
from core.gatekeeper import Gatekeeper
from ai.ollama_client import OllamaClient
from ai.prompts import build_system_prompt
from actions.action_runner import dispatch
from actions import tts
from memory.memory_manager import MemoryManager
from memory.fact_extractor import extract_and_store

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, bus: EventBus, window_monitor, settings):
        self._bus = bus
        self._window_monitor = window_monitor
        self._settings = settings
        self._gatekeeper = Gatekeeper(settings.activation_cooldown_s)
        self._claude = OllamaClient(settings)
        self._memory = MemoryManager(settings.memory_db_path, settings.memory_chroma_path)
        self._queue: asyncio.Queue = asyncio.Queue()
        bus.subscribe("speech", self._queue)

    async def run(self):
        # Initialize memory in background — methods are safe to call before ready
        asyncio.create_task(asyncio.to_thread(self._memory.initialize))
        log.info("Orchestrator ready (memory initializing in background)")
        while True:
            event: SpeechEvent = await self._queue.get()
            asyncio.create_task(self._handle(event))

    async def _handle(self, event: SpeechEvent):
        decision = self._gatekeeper.evaluate(event)
        if not decision.pass_event:
            log.debug("Blocked: %s", decision.reason)
            return

        log.info("User: %r", event.text)

        # Retrieve memory context (runs in thread — ChromaDB inference is blocking)
        recent_turns, relevant = await asyncio.gather(
            asyncio.to_thread(
                self._memory.get_recent_turns, self._settings.memory_recent_turns
            ),
            asyncio.to_thread(
                self._memory.search_relevant, event.text, self._settings.memory_semantic_k
            ),
        )

        window = self._window_monitor.current
        app_context = window.app_class if window else ""
        system = build_system_prompt(window, self._settings, relevant)

        # Conversation history + current turn as messages
        messages = recent_turns + [{"role": "user", "content": event.text}]

        timeout = self._settings.api_timeout_s
        try:
            response = await asyncio.wait_for(
                self._claude.complete(messages, system, dispatch),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            response = "I didn't get a response in time. Please try again."
            log.warning("Ollama timed out after %ss", timeout)
        except Exception as e:
            response = "Something went wrong. Please try again."
            log.exception("Orchestrator error: %s", e)

        log.info("Nyssa: %r", response[:120])

        # Persist turns and index conversation chunk (fire-and-forget)
        turn_id = f"turn_{time.time()}"
        chunk = f"User: {event.text[:200]}\nNyssa: {response[:200]}"
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "user", event.text, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "assistant", response, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.add_chunk, turn_id, chunk))

        # Extract and store facts from this exchange (fire-and-forget)
        asyncio.create_task(
            extract_and_store(event.text, response, self._claude, self._memory, source=turn_id)
        )

        await tts.speak(response, self._settings.tts_voice, self._settings.tts_engine)
