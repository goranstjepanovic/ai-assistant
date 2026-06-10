# Nyssa — Personal AI Assistant

<p align="center">
  <img src="docs/Logo.png" alt="Nyssa" width="120" />
</p>

An always-on Windows voice assistant with full PC awareness. Nyssa listens via microphone, watches the active window, and can respond by voice and execute actions on your PC. All AI inference and memory stay entirely local via Ollama — no data leaves your machine.

## Features

- **Wake word** — say `"hey nyssa"` for hands-free activation
- **Push-to-talk** — hold `Right Alt` to speak from anywhere, including games
- **Conversational follow-up** — after each response, Nyssa stays listening for 30 s so you can reply without repeating the wake word
- **Interrupt** — press the hotkey mid-response to cut Nyssa off and speak immediately
- **Sentence-pipeline TTS** — first audio starts within ~1 s of response arrival; following sentences are pre-synthesized while the current one plays
- **Screen-aware** — captures a screenshot when context requires it ("look at this", game mode, etc.)
- **Persistent local memory** — remembers facts and past conversations across sessions (SQLite + ChromaDB)
- **PC actions** — types text, presses keys, runs shell commands (with voice confirmation), opens URLs, reads/writes clipboard
- **Game-aware** — suppresses wake-word activations in games; hotkey always works
- **System tray** — right-click the tray icon to show/hide the overlay or mute/unmute
- **Local AI** — runs entirely on-device via [Ollama](https://ollama.com/); no API keys required

## Requirements

- Windows 10/11
- Python 3.11+
- [Ollama](https://ollama.com/) running locally with a multimodal model pulled

Recommended model:

```
ollama pull gemma4
```

Any vision-capable model works (`llava`, `gemma4`, `llama3.2-vision`, etc.).

## Quick start

```bat
setup.bat
python main.py
```

Or manually:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

`config/settings.json` is created with defaults on first run.

## Configuration

| Setting | Default | Description |
|---|---|---|
| `wake_word` | `"hey nyssa"` | Hands-free trigger — supports alternatives with `\|`, e.g. `"hey nyssa\|hey lisa"` |
| `hotkey` | `"alt_r"` | Push-to-talk key (also interrupts TTS) |
| `whisper_model` | `"small"` | STT model size: `tiny` · `base` · `small` · `medium` · `large` |
| `tts_voice` | `"en-GB-SoniaNeural"` | Edge TTS voice name |
| `tts_engine` | `"edge-tts"` | `"edge-tts"` or `"pyttsx3"` (fully offline fallback) |
| `ollama_model` | `"gemma4"` | Ollama model name |
| `ollama_host` | `"http://localhost:11434"` | Ollama endpoint |
| `follow_up_window_s` | `30.0` | Seconds Nyssa stays listening after a response (0 to disable) |
| `screen_capture_backend` | `"mss"` | `"mss"` or `"dxcam"` (faster for exclusive-fullscreen games) |
| `symbol_image` | `""` | Path to a PNG/JPG logo shown on the overlay and tray icon |

To add games for suppression, edit `config/game_processes.json`.

## System tray

Nyssa runs in the system tray (bottom-right of taskbar).

| Action | Result |
|---|---|
| Right-click → **Show/Hide Nyssa** | Toggle the overlay widget |
| Right-click → **Mute** | Stop all listening (wake word + hotkey) |
| Double-click tray icon | Toggle show/hide |
| Right-click → **Quit** | Exit |

## Usage tips

- Say **"hey nyssa, open Steam"** — single utterance with command
- Say **"hey nyssa"** alone — Nyssa opens mic and waits for your command
- After any response, just speak — no wake word needed for 30 s
- Press **Right Alt** while Nyssa is speaking to interrupt and start talking

Shell commands always require a voice confirmation before executing.

## Optional: faster game capture

For exclusive-fullscreen games where `mss` can't capture the screen:

```bash
pip install dxcam
```

Then set `"screen_capture_backend": "dxcam"` in `config/settings.json`.

## Project structure

```
nyssa/
├── main.py                  # Entry point
├── config/
│   ├── settings.json        # User config (auto-created)
│   └── game_processes.json  # Game process names for suppression
├── core/
│   ├── event_bus.py         # Async pub/sub + event dataclasses
│   ├── gatekeeper.py        # Activation filter (hotkey, wake word, app class)
│   ├── orchestrator.py      # Main AI loop
│   └── settings.py          # Config loader + validation
├── perception/
│   ├── mic_capture.py       # Whisper + VAD pipeline, wake word, PTT
│   ├── screen_capture.py    # mss / dxcam screenshot wrapper
│   └── window_monitor.py    # Active window detection and classification
├── memory/
│   ├── memory_manager.py    # SQLite + ChromaDB unified API
│   └── fact_extractor.py    # Extracts facts from conversations via Ollama
├── actions/
│   ├── action_runner.py     # Tool call dispatcher + audit log
│   ├── keyboard.py          # Keypress injection (pyautogui / win32api)
│   ├── shell.py             # Shell execution with voice confirmation
│   ├── apps.py              # App launching
│   ├── clipboard.py         # Clipboard read/write
│   ├── search.py            # Web search
│   └── tts.py               # Sentence-pipeline TTS (edge-tts / pyttsx3)
├── ai/
│   ├── ollama_client.py     # Ollama client with tool-use loop
│   ├── tools.py             # Tool definitions (JSON schema)
│   └── prompts.py           # System prompt assembly
├── ui/
│   └── overlay.py           # PyQt6 HUD overlay + system tray
└── logs/
    ├── nyssa.log            # Application log
    └── tool_calls.jsonl     # Audit log for every tool execution
```

## Notes

- Keypress injection into online competitive games is not supported.
- All memory is stored locally in `memory/nyssa.db` and `memory/chroma/`.
- Logs rotate automatically and are capped to keep disk usage low.

## License

[MIT](LICENSE)
