import asyncio
import logging
import os
import queue
import re
import tempfile
from typing import Optional

log = logging.getLogger(__name__)

_pygame_ready = False


def _strip_markdown(text: str) -> str:
    # Code fences — drop the whole block, it won't make sense spoken
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Inline code — keep the content
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Headers — keep the text, drop the # symbols
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold/italic (***,  **, *, ___, __, _)
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)
    # Links — keep the label, drop the URL
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Bullet / numbered list markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Blockquotes
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Collapse leftover whitespace
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()
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
    text = _strip_markdown(text)
    if not text:
        return

    try:
        if engine == "edge-tts":
            try:
                await _speak_edge_tts(text, voice)
                return
            except Exception as e:
                log.warning("edge-tts failed: %s — falling back to pyttsx3", e)

        _ui("state", "speaking")
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
        _ui("state", "speaking")   # set state right before audio starts
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
