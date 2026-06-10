import asyncio
import logging
import os
import queue
import tempfile
from typing import Optional

log = logging.getLogger(__name__)

_pygame_ready = False
_ui_queue: Optional[queue.Queue] = None


def set_ui_queue(q: Optional[queue.Queue]):
    global _ui_queue
    _ui_queue = q


def _ui(kind: str, value):
    if _ui_queue is not None:
        try:
            _ui_queue.put_nowait((kind, value))
        except Exception:
            pass


def _ensure_pygame():
    global _pygame_ready
    if not _pygame_ready:
        import pygame
        pygame.mixer.init()
        _pygame_ready = True


async def speak(text: str, voice: str = "en-GB-SoniaNeural", engine: str = "edge-tts"):
    if not text or not text.strip():
        return

    _ui("state", "speaking")
    try:
        if engine == "edge-tts":
            try:
                await _speak_edge_tts(text, voice)
                return
            except Exception as e:
                log.warning("edge-tts failed: %s — falling back to pyttsx3", e)

        await asyncio.to_thread(_speak_pyttsx3, text)
    finally:
        _ui("state", "idle")


async def _speak_edge_tts(text: str, voice: str):
    import edge_tts

    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(tmp_path)
        await asyncio.to_thread(_play_mp3, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _play_mp3(path: str):
    import pygame
    import time
    _ensure_pygame()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)


def _speak_pyttsx3(text: str):
    import pyttsx3
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def stop():
    try:
        import pygame
        if _pygame_ready:
            pygame.mixer.music.stop()
    except Exception:
        pass
