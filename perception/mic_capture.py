import asyncio
import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd

from core.event_bus import EventBus, SpeechEvent

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MIN_AUDIO_SECONDS = 0.3


def _parse_hotkey(hotkey_str: str) -> tuple[list[str], str]:
    """Split 'alt_r+space' into (['alt_r'], 'space'). Single key → ([], 'key')."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    return parts[:-1], parts[-1]


class MicCapture:
    def __init__(self, bus: EventBus, settings, ui_queue: Optional[queue.Queue] = None):
        self._bus = bus
        self._settings = settings
        self._modifiers, self._trigger = _parse_hotkey(settings.hotkey.lower())
        self._held: set[str] = set()
        self._device = settings.mic_device_index
        self._model = None
        self._recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._transcribing = False
        self._ui_queue = ui_queue

    def _load_model(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        model_size = self._settings.whisper_model
        try:
            self._model = WhisperModel(model_size, device="cuda", compute_type="float16")
            log.info("Whisper '%s' loaded on CUDA", model_size)
        except Exception as e:
            log.warning("CUDA unavailable (%s), falling back to CPU", e)
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            log.info("Whisper '%s' loaded on CPU", model_size)

    def _key_name(self, key) -> str:
        from pynput.keyboard import Key, KeyCode
        if isinstance(key, Key):
            return key.name.lower()
        if isinstance(key, KeyCode) and key.char:
            return key.char.lower()
        return ""

    def _on_press(self, key):
        name = self._key_name(key)
        self._held.add(name)
        if name == self._trigger and not self._recording:
            if all(m in self._held for m in self._modifiers):
                log.debug("Hotkey pressed — recording")
                self._start_recording()

    def _on_release(self, key):
        name = self._key_name(key)
        if name == self._trigger and self._recording:
            log.debug("Hotkey released — transcribing")
            self._stop_and_transcribe()
        self._held.discard(name)

    def _ui(self, kind: str, value):
        if self._ui_queue is not None:
            try:
                self._ui_queue.put_nowait((kind, value))
            except Exception:
                pass

    def _start_recording(self):
        self._recording = True
        self._audio_chunks = []
        self._ui("state", "listening")

        def _callback(indata, frames, time_info, status):
            if status:
                log.debug("Audio status: %s", status)
            if self._recording:
                self._audio_chunks.append(indata.copy())
                rms = float(np.sqrt(np.mean(indata ** 2)))
                self._ui("level", rms)

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self._device,
            callback=_callback,
        )
        self._stream.start()

    def _stop_and_transcribe(self):
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        chunks = self._audio_chunks.copy()
        self._audio_chunks = []

        if chunks:
            self._ui("state", "processing")
            threading.Thread(target=self._transcribe, args=(chunks,), daemon=True).start()
        else:
            self._ui("state", "idle")

    def _transcribe(self, chunks: list[np.ndarray]):
        if self._transcribing:
            log.debug("Already transcribing, skipping")
            return
        self._transcribing = True
        try:
            self._load_model()
            audio = np.concatenate(chunks, axis=0).flatten()

            if len(audio) < SAMPLE_RATE * MIN_AUDIO_SECONDS:
                log.debug("Audio too short (%.2fs), skipping", len(audio) / SAMPLE_RATE)
                self._ui("state", "idle")
                return

            segments, info = self._model.transcribe(
                audio,
                language="en",
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip()

            if not text:
                log.debug("Empty transcription")
                self._ui("state", "idle")
                return

            log.info("Transcribed: %r (lang=%.0f%%)", text, info.language_probability * 100)
            event = SpeechEvent(
                text=text,
                timestamp=time.time(),
                confidence=info.language_probability,
                hotkey_triggered=True,
            )
            self._bus.publish_threadsafe("speech", event)
        except Exception:
            log.exception("Transcription failed")
            self._ui("state", "idle")
        finally:
            self._transcribing = False

    async def run(self):
        from pynput import keyboard as kb
        combo = "+".join(self._modifiers + [self._trigger]).upper()
        log.info("MicCapture started — hold [%s] to speak", combo)
        log.info("Loading Whisper model in background...")
        asyncio.get_running_loop().run_in_executor(None, self._load_model)

        listener = kb.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.start()
        try:
            while True:
                await asyncio.sleep(1)
        finally:
            listener.stop()
