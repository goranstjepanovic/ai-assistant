import time
import logging
from core.event_bus import SpeechEvent, GatekeeperDecision, WindowChangeEvent

log = logging.getLogger(__name__)

_SCREENSHOT_PHRASES = (
    "look at",
    "what's on screen",
    "what is on screen",
    "what am i looking at",
    "help me with this",
    "can you see",
    "what do you see",
    "what's on my screen",
    "what is on my screen",
    "see this",
    "read this",
    "what is this",
    "what's this",
)


class Gatekeeper:
    def __init__(self, cooldown_s: float = 1.5):
        self._cooldown = cooldown_s
        self._last_activation = 0.0

    def evaluate(
        self,
        event: SpeechEvent,
        window: WindowChangeEvent | None = None,
    ) -> GatekeeperDecision:
        now = time.monotonic()
        elapsed = now - self._last_activation

        if elapsed < self._cooldown:
            log.debug("Cooldown: %.1fs remaining", self._cooldown - elapsed)
            return GatekeeperDecision(
                pass_event=False,
                include_screenshot=False,
                reason=f"cooldown ({self._cooldown - elapsed:.1f}s remaining)",
            )

        self._last_activation = now

        text_lower = event.text.lower()
        phrase_match = any(p in text_lower for p in _SCREENSHOT_PHRASES)
        game_mode = window is not None and window.app_class == "game"
        include_screenshot = phrase_match or game_mode

        if include_screenshot:
            reason = "game mode" if game_mode else "screenshot phrase"
            log.debug("Screenshot triggered: %s", reason)

        return GatekeeperDecision(
            pass_event=True,
            include_screenshot=include_screenshot,
            reason="hotkey",
        )
