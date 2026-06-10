import asyncio
import logging
import os
import subprocess

from actions import tts

log = logging.getLogger(__name__)

_confirm_queue: asyncio.Queue | None = None


def pending() -> bool:
    return _confirm_queue is not None


async def respond(text: str):
    if _confirm_queue is not None:
        try:
            _confirm_queue.put_nowait(text)
        except asyncio.QueueFull:
            pass


async def run_shell(
    command: str,
    working_dir: str = "~",
    voice: str = "en-GB-SoniaNeural",
    engine: str = "edge-tts",
) -> str:
    global _confirm_queue

    prompt = f"I need to run this command: {command}. Say yes to confirm."
    await tts.speak(prompt, voice, engine)

    _confirm_queue = asyncio.Queue(maxsize=1)
    try:
        response = await asyncio.wait_for(_confirm_queue.get(), timeout=15.0)
    except asyncio.TimeoutError:
        return "Confirmation timed out. Command was not executed."
    finally:
        _confirm_queue = None

    if "yes" not in response.lower():
        return "Command cancelled."

    cwd = os.path.expanduser(working_dir) if working_dir else None
    log.info("run_shell: %r (cwd=%s)", command, cwd)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )
        output = (proc.stdout + proc.stderr).strip()
        return output[:1500] if output else "Command completed with no output."
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds."
    except Exception as e:
        return f"Command failed: {e}"
