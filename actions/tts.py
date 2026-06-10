import asyncio
import logging
import os
import queue
import re
import tempfile
import threading
from typing import Optional

log = logging.getLogger(__name__)

_pygame_ready = False
_ui_queue: Optional[queue.Queue] = None
_stop_event = threading.Event()
_speaking = False


def set_ui_queue(q: Optional[queue.Queue]):
    global _ui_queue
    _ui_queue = q


def _ui(kind: str, value):
    if _ui_queue is not None:
        try:
            _ui_queue.put_nowait((kind, value))
        except Exception:
            pass


def is_speaking() -> bool:
    return _speaking


def stop():
    """Interrupt any in-progress speech immediately."""
    _stop_event.set()
    try:
        import pygame
        if _pygame_ready:
            pygame.mixer.music.stop()
    except Exception:
        pass


def _ensure_pygame():
    global _pygame_ready
    if not _pygame_ready:
        import pygame
        pygame.mixer.init()
        _pygame_ready = True


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


def _split_sentences(text: str) -> list[str]:
    # Split at sentence-ending punctuation followed by whitespace
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


async def speak_stream(
    chunk_gen,
    voice: str = "en-GB-SoniaNeural",
    engine: str = "edge-tts",
) -> str:
    """
    Consume an async generator of text chunks, pipeline sentences to TTS.

    Sentences are synthesized as soon as they arrive; the player waits for
    each audio to finish before starting the next — like a playlist that
    forms while it plays.  Returns the full response text.
    """
    global _speaking
    _stop_event.clear()
    _speaking = True
    try:
        if engine == "edge-tts":
            try:
                return await _speak_stream_pipeline(chunk_gen, voice)
            except Exception as e:
                log.warning("edge-tts streaming failed: %s — falling back to pyttsx3", e)
                # chunk_gen already exhausted at this point; fall through
                return ""
        else:
            parts: list[str] = []
            async for chunk in chunk_gen:
                parts.append(chunk)
            text = _strip_markdown("".join(parts))
            if text:
                _ui("state", "speaking")
                await asyncio.to_thread(_speak_pyttsx3, text)
            return text
    finally:
        _speaking = False
        _ui("state", "idle")


async def _speak_stream_pipeline(chunk_gen, voice: str) -> str:
    """
    Producer: collects chunks → sentences → kicks off synthesis tasks.
    Player:   awaits each task in order → plays → moves to next.
    Both run concurrently via asyncio.gather.
    """
    synth_q: asyncio.Queue = asyncio.Queue()  # asyncio.Task | None
    text_parts: list[str] = []

    async def producer():
        buf = ""
        async for chunk in chunk_gen:
            if _stop_event.is_set():
                break
            text_parts.append(chunk)
            buf += chunk
            # Flush any complete sentences
            while True:
                m = re.search(r"(?<=[.!?])\s+", buf)
                if not m:
                    break
                sentence = _strip_markdown(buf[: m.end()])
                buf = buf[m.end():]
                if sentence:
                    await synth_q.put(asyncio.create_task(_synthesize(sentence, voice)))
        # Flush remainder
        if buf.strip() and not _stop_event.is_set():
            sentence = _strip_markdown(buf)
            if sentence:
                await synth_q.put(asyncio.create_task(_synthesize(sentence, voice)))
        await synth_q.put(None)  # sentinel — playlist is complete

    async def player():
        _ui("state", "speaking")
        while True:
            item = await synth_q.get()
            if item is None:
                break  # playlist finished
            try:
                path = await item  # wait for this track to be ready
            except Exception as e:
                log.warning("Synthesis failed: %s", e)
                continue
            await asyncio.to_thread(_play_mp3, path)  # play; blocks until done
            try:
                os.unlink(path)
            except OSError:
                pass
            if _stop_event.is_set():
                # Drain and cancel any remaining queued tracks
                while True:
                    try:
                        remaining = synth_q.get_nowait()
                        if remaining is not None:
                            remaining.cancel()
                            try:
                                await remaining
                            except (asyncio.CancelledError, Exception):
                                pass
                    except asyncio.QueueEmpty:
                        break
                break

    await asyncio.gather(producer(), player())
    return _strip_markdown("".join(text_parts))


async def speak(text: str, voice: str = "en-GB-SoniaNeural", engine: str = "edge-tts"):
    global _speaking
    text = _strip_markdown(text)
    if not text:
        return

    _stop_event.clear()
    _speaking = True
    try:
        if engine == "edge-tts":
            try:
                await _speak_edge_tts_pipelined(text, voice)
                return
            except Exception as e:
                log.warning("edge-tts failed: %s — falling back to pyttsx3", e)

        _ui("state", "speaking")
        await asyncio.to_thread(_speak_pyttsx3, text)
    finally:
        _speaking = False
        _ui("state", "idle")


async def _synthesize(text: str, voice: str) -> str:
    """Synthesize one sentence to a temp MP3, return path."""
    import edge_tts
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    path = tmp.name
    tmp.close()
    await edge_tts.Communicate(text, voice).save(path)
    return path


async def _speak_edge_tts_pipelined(text: str, voice: str):
    """
    Sentence pipeline: while sentence N is playing, sentence N+1 is being
    synthesized — so time-to-first-audio equals one sentence synthesis time
    regardless of total response length.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return

    _ui("state", "speaking")

    # Kick off synthesis of the first sentence immediately
    next_synth: asyncio.Task = asyncio.create_task(_synthesize(sentences[0], voice))

    for i in range(len(sentences)):
        if _stop_event.is_set():
            next_synth.cancel()
            try:
                await next_synth
            except (asyncio.CancelledError, Exception):
                pass
            break

        # Wait for this sentence's audio (usually already done by the time we get here)
        try:
            path = await next_synth
        except Exception as e:
            log.warning("Synthesis failed for sentence %d: %s", i, e)
            break

        # Pre-synthesize the next sentence while this one plays
        if i + 1 < len(sentences):
            next_synth = asyncio.create_task(_synthesize(sentences[i + 1], voice))

        # Play and clean up
        await asyncio.to_thread(_play_mp3, path)
        try:
            os.unlink(path)
        except OSError:
            pass

        if _stop_event.is_set():
            if i + 1 < len(sentences):
                next_synth.cancel()
                try:
                    await next_synth
                except (asyncio.CancelledError, Exception):
                    pass
            break


def _play_mp3(path: str):
    import pygame
    import time
    _ensure_pygame()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy() and not _stop_event.is_set():
        time.sleep(0.05)
    if _stop_event.is_set():
        pygame.mixer.music.stop()


def _speak_pyttsx3(text: str):
    import pyttsx3
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
