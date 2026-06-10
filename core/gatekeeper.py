import time
import logging
from core.event_bus import SpeechEvent, GatekeeperDecision

log = logging.getLogger(__name__)


class Gatekeeper:
    def __init__(self, cooldown_s: float = 1.5):
        self._cooldown = cooldown_s
        self._last_activation = 0.0

    def evaluate(self, event: SpeechEvent) -> GatekeeperDecision:
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
        return GatekeeperDecision(
            pass_event=True,
            include_screenshot=False,
            reason="hotkey",
        )
