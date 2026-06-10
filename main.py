import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

# Suppress Qt's benign DPI-awareness warning on Windows.
# Python sets process DPI awareness before Qt can, so Qt's attempt to set it
# gets ERROR_ACCESS_DENIED — harmless, but noisy.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window.warning=false")

from core.event_bus import EventBus
from core.settings import load_settings
from core.orchestrator import Orchestrator
from perception.window_monitor import WindowMonitor
from perception.mic_capture import MicCapture
from actions import tts as tts_module


def setup_logging(level: str, log_dir: str):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s %(name)-22s %(levelname)-8s %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"{log_dir}/nyssa.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=handlers,
    )


async def _backend(settings, ui_queue, mute_flag: threading.Event):
    log = logging.getLogger("nyssa")
    bus = EventBus()
    loop = asyncio.get_running_loop()
    bus.set_loop(loop)

    if ui_queue is not None:
        tts_module.set_ui_queue(ui_queue)

    window_monitor = WindowMonitor(bus, settings.window_poll_interval_ms)
    mic_capture = MicCapture(bus, settings, ui_queue, mute_flag=mute_flag)
    orchestrator = Orchestrator(bus, window_monitor, settings)

    try:
        await asyncio.gather(
            window_monitor.run(),
            mic_capture.run(),
            orchestrator.run(),
        )
    except asyncio.CancelledError:
        log.info("Nyssa stopped.")


if __name__ == "__main__":
    settings = load_settings()
    setup_logging(settings.log_level, settings.log_dir)
    log = logging.getLogger("nyssa")

    log.info("=" * 60)
    log.info("Nyssa starting up")
    log.info("Model : %s @ %s", settings.ollama_model, settings.ollama_host)
    log.info("Voice : %s", settings.tts_voice)
    log.info("Hotkey: %s (push-to-talk)", settings.hotkey.upper())
    log.info("=" * 60)

    mute_flag = threading.Event()

    try:
        import queue as _queue
        from PyQt6.QtWidgets import QApplication
        from ui.overlay import OverlayWidget

        ui_queue = _queue.Queue()

        # Asyncio backend in a daemon thread so it dies when Qt exits
        threading.Thread(
            target=asyncio.run,
            args=(_backend(settings, ui_queue, mute_flag),),
            daemon=True,
        ).start()

        # Qt must run on the main thread
        app = QApplication(sys.argv)
        widget = OverlayWidget(
            ui_queue,
            symbol_path=getattr(settings, "symbol_image", ""),
            mute_flag=mute_flag,
        )
        sys.exit(app.exec())

    except ImportError:
        log.info("PyQt6 not installed — running headless (pip install PyQt6 to enable UI)")
        try:
            asyncio.run(_backend(settings, None, mute_flag))
        except KeyboardInterrupt:
            print("\nNyssa stopped.")
