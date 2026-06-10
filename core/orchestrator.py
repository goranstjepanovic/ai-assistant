import asyncio
import logging
import time

from core.event_bus import EventBus, SpeechEvent
from core.gatekeeper import Gatekeeper
from ai.ollama_client import OllamaClient
from ai.prompts import build_system_prompt
from actions.action_runner import ActionRunner
from actions import shell as _shell
from actions import tts
from memory.memory_manager import MemoryManager
from memory.fact_extractor import extract_and_store
from perception.screen_capture import capture_now

log = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, bus: EventBus, window_monitor, settings):
        self._bus = bus
        self._window_monitor = window_monitor
        self._settings = settings
        self._gatekeeper = Gatekeeper(settings.activation_cooldown_s)
        self._claude = OllamaClient(settings)
        self._memory = MemoryManager(settings.memory_db_path, settings.memory_chroma_path)
        self._action_runner = ActionRunner(memory=self._memory, settings=settings)
        self._queue: asyncio.Queue = asyncio.Queue()
        bus.subscribe("speech", self._queue)

    async def run(self):
        asyncio.create_task(asyncio.to_thread(self._memory.initialize))
        log.info("Orchestrator ready (memory initializing in background)")
        while True:
            event: SpeechEvent = await self._queue.get()
            asyncio.create_task(self._handle(event))

    async def _handle(self, event: SpeechEvent):
        # Confirmation responses go directly to the shell module, skip normal flow
        if _shell.pending():
            await _shell.respond(event.text)
            return

        window = self._window_monitor.current
        decision = self._gatekeeper.evaluate(event, window)
        if not decision.pass_event:
            log.debug("Blocked: %s", decision.reason)
            return

        log.info("User: %r", event.text)

        recent_turns, relevant = await asyncio.gather(
            asyncio.to_thread(
                self._memory.get_recent_turns, self._settings.memory_recent_turns
            ),
            asyncio.to_thread(
                self._memory.search_relevant, event.text, self._settings.memory_semantic_k
            ),
        )

        app_context = window.app_class if window else ""
        screenshot_attached = False
        user_message: dict = {"role": "user", "content": event.text}

        if decision.include_screenshot:
            try:
                resize = tuple(self._settings.screenshot_resize)
                quality = self._settings.screenshot_quality
                screenshot = await asyncio.to_thread(capture_now, resize, quality)
                user_message["images"] = [screenshot]
                screenshot_attached = True
                log.info("Screenshot attached (%d KB)", len(screenshot) // 1024)
            except Exception:
                log.exception("Screen capture failed — continuing without screenshot")

        system = build_system_prompt(window, self._settings, relevant, has_screenshot=screenshot_attached)

        messages = recent_turns + [user_message]

        timeout = self._settings.api_timeout_s
        try:
            response = await asyncio.wait_for(
                self._claude.complete(messages, system, self._action_runner.dispatch),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            response = "I didn't get a response in time. Please try again."
            log.warning("Ollama timed out after %ss", timeout)
        except Exception as e:
            response = "Something went wrong. Please try again."
            log.exception("Orchestrator error: %s", e)

        log.info("Nyssa: %r", response[:120])

        turn_id = f"turn_{time.time()}"
        chunk = f"User: {event.text[:200]}\nNyssa: {response[:200]}"
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "user", event.text, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "assistant", response, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.add_chunk, turn_id, chunk))

        asyncio.create_task(
            extract_and_store(event.text, response, self._claude, self._memory, source=turn_id)
        )

        await tts.speak(response, self._settings.tts_voice, self._settings.tts_engine)
