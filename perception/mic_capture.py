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

# Always-on wake word listener tuning
_WW_CHUNK_SECS = 0.1
_WW_SPEECH_RMS = 0.015       # energy threshold to classify as speech
_WW_SILENCE_END = 15         # chunks of silence to end a segment (~1.5 s)
_WW_MAX_SECS = 8.0           # hard cap per segment


# Map pynput key names to the canonical names used in config.
# Left/right variants collapse to a single name; AltGr → alt_r.
_KEY_CANONICAL: dict[str, str] = {
    "ctrl_l":  "ctrl",  "ctrl_r":  "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l":   "alt",
    "alt_gr":  "alt_r",   # AltGr on European keyboards
    "cmd_l":   "win",   "cmd_r":   "win",
    "super_l": "win",   "super_r": "win",
}


def _parse_hotkey(hotkey_str: str) -> tuple[list[str], str]:
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
        self._model_lock = threading.Lock()
        self._recording = False
        self._audio_chunks: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._transcribing = False
        self._ui_queue = ui_queue

    # ── Model loading ─────────────────────────────────────────────────────────

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

    # ── UI helper ─────────────────────────────────────────────────────────────

    def _ui(self, kind: str, value):
        if self._ui_queue is not None:
            try:
                self._ui_queue.put_nowait((kind, value))
            except Exception:
                pass

    # ── Hotkey push-to-talk ───────────────────────────────────────────────────

    def _key_name(self, key) -> str:
        from pynput.keyboard import Key, KeyCode
        if isinstance(key, Key):
            raw = key.name.lower()
            return _KEY_CANONICAL.get(raw, raw)
        if isinstance(key, KeyCode) and key.char:
            return key.char.lower()
        return ""

    def _on_press(self, key):
        name = self._key_name(key)
        if not name:
            return
        log.debug("key press: %r  held=%s", name, self._held)
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
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            device=self._device, callback=_callback,
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

            with self._model_lock:
                segments, info = self._model.transcribe(
                    audio, language="en", beam_size=5, vad_filter=True,
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

    # ── Always-on wake word listener ──────────────────────────────────────────

    def _check_wakeword(self, audio: np.ndarray, wake: str):
        if len(audio) < SAMPLE_RATE * 0.5:
            return
        self._load_model()
        with self._model_lock:
            segments, _ = self._model.transcribe(
                audio, language="en", beam_size=3, vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip().lower()

        if not text:
            return

        log.debug("Wake word check: %r", text)
        idx = text.find(wake)
        if idx == -1:
            return

        command = text[idx + len(wake):].strip(" ,.")
        if not command:
            log.debug("Wake word detected but no command followed")
            return

        log.info("Wake word: command = %r", command)
        event = SpeechEvent(
            text=command,
            timestamp=time.time(),
            confidence=0.8,
            hotkey_triggered=False,
        )
        self._bus.publish_threadsafe("speech", event)

    async def _run_wakeword_listener(self):
        wake = self._settings.wake_word.lower().strip()
        chunk_size = int(SAMPLE_RATE * _WW_CHUNK_SECS)

        raw_q: queue.Queue = queue.Queue(maxsize=200)

        def _cb(indata, frames, time_info, status):
            if not self._recording:
                try:
                    raw_q.put_nowait(indata.copy())
                except queue.Full:
                    pass

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            device=self._device, callback=_cb, blocksize=chunk_size,
        )
        stream.start()
        log.info("Wake word listener active — say %r to activate", self._settings.wake_word)

        segment: list[np.ndarray] = []
        silence_count = 0
        in_speech = False

        try:
            while True:
                # Drain queue without blocking the event loop
                drained = []
                while True:
                    try:
                        drained.append(raw_q.get_nowait())
                    except queue.Empty:
                        break

                if not drained:
                    await asyncio.sleep(_WW_CHUNK_SECS)
                    continue

                for chunk in drained:
                    rms = float(np.sqrt(np.mean(chunk ** 2)))

                    if rms >= _WW_SPEECH_RMS:
                        segment.append(chunk)
                        silence_count = 0
                        in_speech = True
                    elif in_speech:
                        segment.append(chunk)
                        silence_count += 1

                        total_secs = len(segment) * _WW_CHUNK_SECS
                        if silence_count >= _WW_SILENCE_END or total_secs >= _WW_MAX_SECS:
                            audio = np.concatenate(segment, axis=0).flatten()
                            segment = []
                            silence_count = 0
                            in_speech = False
                            asyncio.create_task(
                                asyncio.to_thread(self._check_wakeword, audio, wake)
                            )
        finally:
            stream.stop()
            stream.close()

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run(self):
        from pynput import keyboard as kb

        combo = "+".join(self._modifiers + [self._trigger]).upper()
        log.info("MicCapture started — hold [%s] to speak", combo)
        log.info("Loading Whisper model in background...")
        asyncio.get_running_loop().run_in_executor(None, self._load_model)

        listener = kb.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.start()
        try:
            wake = self._settings.wake_word.strip() if hasattr(self._settings, "wake_word") else ""
            if wake:
                await self._run_wakeword_listener()
            else:
                log.info("Wake word disabled — push-to-talk only")
                while True:
                    await asyncio.sleep(1)
        finally:
            listener.stop()
