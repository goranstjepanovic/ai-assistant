import asyncio
import logging

import numpy as np
import sounddevice as sd

from actions import tts

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_RECORD_SECS = 5
_PHRASES = [
    "The quick brown fox jumps over the lazy dog.",
    "Testing, one, two, three, four, five.",
    "This is my voice. I speak clearly and naturally.",
]


async def _record_clip(device_index) -> np.ndarray:
    n_samples = _SAMPLE_RATE * _RECORD_SECS
    audio = await asyncio.to_thread(
        sd.rec,
        n_samples,
        samplerate=_SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=device_index,
        blocking=True,
    )
    return audio.flatten()


async def enroll_speaker(name: str, settings) -> str:
    from perception import speaker_id as _speaker_id

    sid = _speaker_id.get_instance()
    if sid is None:
        return "Speaker identification is not initialised."

    voice = settings.tts_voice
    engine = settings.tts_engine
    device = settings.mic_device_index
    total = len(_PHRASES)
    samples: list[np.ndarray] = []

    await tts.speak(
        f"I'll learn your voice now. I'll ask you to say {total} phrases. "
        "Speak clearly after each prompt.",
        voice,
        engine,
    )

    for i, phrase in enumerate(_PHRASES, 1):
        await tts.speak(
            f"Phrase {i} of {total}. Say: {phrase}",
            voice,
            engine,
        )
        await asyncio.sleep(0.4)  # brief gap so playback device releases
        audio = await _record_clip(device)
        samples.append(audio)
        await tts.speak("Got it.", voice, engine)

    success = await asyncio.to_thread(sid.enroll, name, samples)
    if success:
        return f"Voice enrolled for {name}. I'll recognise you from now on."
    return "Enrollment failed. Please try again in a quiet environment."
