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
    "follow_up_window_s": 30.0,
    "system_audio_suppress_threshold": 0.6,
    "memory_recent_turns": 10,
    "memory_semantic_k": 5,
    "max_tool_calls_per_turn": 10,
    "ollama_model": "gemma4",
    "ollama_host": "http://localhost:11434",
    "api_timeout_s": 300.0,
    "ollama_inactivity_timeout_s": 45.0,
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


_VALIDATIONS = [
    # (field, type_or_types, extra_check, hint)
    ("wake_word",               str,         None,                   "must be a non-empty string, e.g. 'hey nyssa'"),
    ("hotkey",                  str,         None,                   "must be a key name, e.g. 'alt_r' or 'ctrl+shift+n'"),
    ("whisper_model",           str,         lambda v: v in ("tiny","base","small","medium","large","large-v2","large-v3"),
                                                                     "must be one of: tiny, base, small, medium, large, large-v2, large-v3"),
    ("activation_cooldown_s",   (int,float), lambda v: v >= 0,      "must be a non-negative number"),
    ("follow_up_window_s",      (int,float), lambda v: v >= 0,      "must be a non-negative number"),
    ("memory_recent_turns",     int,         lambda v: v > 0,       "must be a positive integer"),
    ("memory_semantic_k",       int,         lambda v: v > 0,       "must be a positive integer"),
    ("max_tool_calls_per_turn", int,         lambda v: v > 0,       "must be a positive integer"),
    ("api_timeout_s",           (int,float), lambda v: v > 0,       "must be a positive number"),
    ("ollama_inactivity_timeout_s", (int,float), lambda v: v > 0,  "must be a positive number"),
    ("screenshot_quality",      int,         lambda v: 1 <= v <= 95,"must be between 1 and 95"),
    ("tts_engine",              str,         lambda v: v in ("edge-tts","pyttsx3"),
                                                                     "must be 'edge-tts' or 'pyttsx3'"),
    ("ollama_host",             str,         lambda v: v.startswith("http"),
                                                                     "must be a URL, e.g. 'http://localhost:11434'"),
]


def validate_settings(settings: "Settings") -> list[str]:
    errors = []
    for field, types, check, hint in _VALIDATIONS:
        val = getattr(settings, field, None)
        if val is None:
            errors.append(f"  {field}: missing — {hint}")
            continue
        if not isinstance(val, types):
            errors.append(f"  {field}: expected {types}, got {type(val).__name__} — {hint}")
            continue
        if check and not check(val):
            errors.append(f"  {field}: invalid value {val!r} — {hint}")
    return errors


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

    settings = Settings(merged)
    errors = validate_settings(settings)
    if errors:
        print("Config validation warnings:")
        for e in errors:
            print(e)
    return settings
