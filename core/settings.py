import json
import os
from pathlib import Path

DEFAULTS = {
    "assistant_name": "Nyssa",
    "wake_word": "hey nyssa",
    "hotkey": "alt_r",
    "mic_device_index": None,
    "whisper_model": "small",
    "vad_threshold": 0.7,
    "tts_voice": "en-GB-SoniaNeural",
    "tts_engine": "edge-tts",
    "audio_output_device": None,
    "symbol_image": "",
    "screen_capture_backend": "mss",
    "screen_capture_monitor": -1,
    "screenshot_resize": [1280, 720],
    "screenshot_quality": 75,
    "window_poll_interval_ms": 500,
    "activation_cooldown_s": 1.5,
    "system_audio_suppress_threshold": 0.6,
    "memory_recent_turns": 10,
    "memory_semantic_k": 5,
    "max_tool_calls_per_turn": 10,
    "ollama_model": "gemma4",
    "ollama_host": "http://localhost:11434",
    "api_timeout_s": 60.0,
    "memory_db_path": "memory/nyssa.db",
    "memory_chroma_path": "memory/chroma",
    "log_level": "INFO",
    "log_dir": "logs",
}

CONFIG_PATH = Path("config/settings.json")


class Settings:
    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


def load_settings() -> Settings:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        merged = {**DEFAULTS, **data}
    else:
        merged = DEFAULTS.copy()
        with open(CONFIG_PATH, "w") as f:
            json.dump(merged, f, indent=2)
        print(f"Created default config at {CONFIG_PATH}")
    return Settings(merged)
