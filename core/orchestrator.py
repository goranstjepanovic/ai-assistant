import asyncio
import logging
import time

from core.event_bus import EventBus, SpeechEvent, FollowUpEvent, TtsStartEvent
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
        await asyncio.to_thread(self._memory.initialize)
        from perception import speaker_id as _speaker_id
        threshold = getattr(self._settings, "speaker_id_threshold", 0.72)
        _speaker_id.init(self._memory, threshold)
        log.info("Orchestrator ready")
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

        log.info("User [%s]: %r", event.speaker or "unknown", event.text)

        recent_turns, relevant, relationship = await asyncio.gather(
            asyncio.to_thread(
                self._memory.get_recent_turns, self._settings.memory_recent_turns
            ),
            asyncio.to_thread(
                self._memory.search_relevant, event.text, self._settings.memory_semantic_k
            ),
            asyncio.to_thread(self._memory.get_relationship_facts),
        )

        app_context = window.app_class if window else ""
        screenshot_attached = False
        user_message: dict = {"role": "user", "content": event.text}

        if decision.include_screenshot:
            try:
                resize = tuple(self._settings.screenshot_resize)
                quality = self._settings.screenshot_quality
                monitor = getattr(self._settings, "screen_capture_monitor", -1)
                backend = getattr(self._settings, "screen_capture_backend", "mss")
                screenshot = await asyncio.to_thread(capture_now, resize, quality, monitor, backend)
                user_message["images"] = [screenshot]
                screenshot_attached = True
                log.info("Screenshot attached (%d KB)", len(screenshot) // 1024)
            except Exception:
                log.exception("Screen capture failed — continuing without screenshot")

        system = build_system_prompt(
            window, self._settings, relevant, relationship,
            has_screenshot=screenshot_attached,
            speaker=event.speaker,
        )

        messages = recent_turns + [user_message]

        timeout = self._settings.api_timeout_s
        voice = self._settings.tts_voice
        engine = self._settings.tts_engine
        follow_up_s = getattr(self._settings, "follow_up_window_s", 0.0)

        response = ""
        await self._bus.publish("tts_start", TtsStartEvent())
        try:
            response = await asyncio.wait_for(
                tts.speak_stream(
                    self._claude.stream_complete(
                        messages, system, self._action_runner.dispatch
                    ),
                    voice,
                    engine,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            response = "I didn't get a response in time. Please try again."
            log.warning("Ollama timed out after %ss", timeout)
            tts.stop()
            await tts.speak(response, voice, engine)
        except Exception as e:
            response = "Something went wrong. Please try again."
            log.exception("Orchestrator error: %s", e)
            await tts.speak(response, voice, engine)
        finally:
            await self._bus.publish("follow_up", FollowUpEvent(duration_s=follow_up_s))

        if not response:
            return

        log.info("Nyssa: %r", response[:120])

        turn_id = f"turn_{time.time()}"
        mem_chunk = f"User: {event.text[:200]}\nNyssa: {response[:200]}"
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "user", event.text, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.write_turn, "assistant", response, app_context))
        asyncio.create_task(asyncio.to_thread(self._memory.add_chunk, turn_id, mem_chunk))

        asyncio.create_task(
            extract_and_store(event.text, response, self._claude, self._memory, source=turn_id)
        )
