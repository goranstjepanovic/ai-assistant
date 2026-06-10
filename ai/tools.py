# OpenAI-compatible tool format (used by Ollama)
TOOLS = [
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
