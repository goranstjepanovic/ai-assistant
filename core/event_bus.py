import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpeechEvent:
    text: str
    timestamp: float
    confidence: float
    hotkey_triggered: bool = True


@dataclass
class WindowChangeEvent:
    process_name: str
    window_title: str
    app_class: str


@dataclass
class GatekeeperDecision:
    pass_event: bool
    include_screenshot: bool
    reason: str


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def subscribe(self, topic: str, queue: asyncio.Queue):
        self._subscribers[topic].append(queue)

    async def publish(self, topic: str, event: Any):
        for queue in self._subscribers[topic]:
            await queue.put(event)

    def publish_threadsafe(self, topic: str, event: Any):
        if self._loop is None:
            return
        for queue in self._subscribers[topic]:
            self._loop.call_soon_threadsafe(queue.put_nowait, event)
