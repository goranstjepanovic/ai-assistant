import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_DEFAULT_THRESHOLD = 0.65


class SpeakerIdentifier:
    def __init__(self, memory, threshold: float = _DEFAULT_THRESHOLD):
        self._memory = memory
        self._threshold = threshold
        self._encoder = None
        self._profiles: dict[str, np.ndarray] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def _load_encoder(self):
        if self._encoder is not None:
            return
        from resemblyzer import VoiceEncoder
        self._encoder = VoiceEncoder(device="cpu")
        log.info("Speaker encoder loaded (CPU)")

    def _ensure_profiles(self):
        if self._loaded:
            return
        try:
            self._profiles = self._memory.get_speakers()
            self._loaded = True
            log.info("Speaker profiles loaded: %s", list(self._profiles.keys()) or "none")
        except Exception:
            log.debug("Could not load speaker profiles yet", exc_info=True)

    def identify(self, audio: np.ndarray) -> tuple[str, float] | None:
        with self._lock:
            self._ensure_profiles()
            if not self._profiles:
                return None
            self._load_encoder()
        try:
            from resemblyzer import preprocess_wav
            wav = preprocess_wav(audio, source_sr=_SAMPLE_RATE)
            embedding = self._encoder.embed_utterance(wav)
        except Exception:
            log.debug("Speaker ID embedding failed", exc_info=True)
            return None

        best_name, best_score = None, -1.0
        with self._lock:
            for name, ref in self._profiles.items():
                norm = np.linalg.norm(embedding) * np.linalg.norm(ref)
                if norm == 0:
                    continue
                score = float(np.dot(embedding, ref) / norm)
                if score > best_score:
                    best_score, best_name = score, name

        if best_score >= self._threshold:
            log.info("Speaker identified: %s (score=%.3f)", best_name, best_score)
            return best_name, best_score

        log.info("Speaker unknown (best=%s score=%.3f threshold=%.2f)", best_name, best_score, self._threshold)
        return None

    def enroll(self, name: str, audio_samples: list[np.ndarray]) -> bool:
        if not audio_samples:
            return False
        try:
            self._load_encoder()
            from resemblyzer import preprocess_wav
            embeddings = []
            for audio in audio_samples:
                wav = preprocess_wav(audio, source_sr=_SAMPLE_RATE)
                embeddings.append(self._encoder.embed_utterance(wav))
            avg = np.mean(embeddings, axis=0).astype(np.float32)
            norm = np.linalg.norm(avg)
            if norm > 0:
                avg /= norm
            self._memory.save_speaker(name, avg)
            with self._lock:
                self._profiles[name] = avg
            log.info("Speaker enrolled: %s (%d sample(s))", name, len(audio_samples))
            return True
        except Exception:
            log.exception("Enrollment failed for %s", name)
            return False


# ── Module-level singleton ────────────────────────────────────────────────────

_instance: SpeakerIdentifier | None = None


def init(memory, threshold: float = _DEFAULT_THRESHOLD) -> SpeakerIdentifier:
    global _instance
    _instance = SpeakerIdentifier(memory, threshold)
    return _instance


def get_instance() -> SpeakerIdentifier | None:
    return _instance
