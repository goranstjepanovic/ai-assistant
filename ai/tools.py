# OpenAI-compatible tool format (used by Ollama)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_apps",
            "description": (
                "Return a list of installed applications from the Start Menu. "
                "Call this when the user asks to open an app and you're unsure of the exact name."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": (
                "Open an installed application by name. "
                "Uses fuzzy matching so 'chrome', 'Google Chrome', or 'Chrome' all work. "
                "If unsure of the name, call list_apps first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The application name, e.g. 'Spotify', 'Chrome', 'VS Code'",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently active window as if typed on the keyboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to type",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": (
                "Press a key or key combination. "
                "Examples: 'ctrl+c', 'ctrl+v', 'enter', 'escape', 'tab', 'f5', 'alt+f4'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key name or combination joined with '+', e.g. 'ctrl+c'",
                    },
                },
                "required": ["key"],
            },
        },
    },
]
