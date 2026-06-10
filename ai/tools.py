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
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo and return titles, URLs, and snippets. "
                "Use this for current events, facts you're unsure about, prices, weather, "
                "documentation, or anything that may have changed since your training."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open a URL in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to open"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_clipboard",
            "description": "Read and return the current clipboard text content.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_clipboard",
            "description": "Write text to the clipboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to copy"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": (
                "Store a persistent fact or preference about the user for future reference. "
                "Use a short snake_case key, e.g. 'preferred_browser', 'user_name'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short identifier"},
                    "value": {"type": "string", "description": "The value to store"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command and return its output. "
                "ALWAYS requires the user to say 'yes' to confirm before executing. "
                "Use for tasks like running scripts, opening files via CLI, or system operations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory, defaults to home (~)",
                    },
                },
                "required": ["command"],
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
            "name": "send_keys_to_window",
            "description": (
                "Send a key or key combination to a specific application window "
                "without changing focus. Useful for controlling games or background apps. "
                "Examples: press 'f' in 'minecraft' while doing something else."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "description": "Process name, e.g. 'minecraft', 'notepad', 'chrome'",
                    },
                    "key": {
                        "type": "string",
                        "description": "Key or combo, e.g. 'f', 'ctrl+s', 'escape'",
                    },
                },
                "required": ["process_name", "key"],
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
