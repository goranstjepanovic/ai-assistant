import asyncio
import json
import logging

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are a fact extractor. Given a short conversation, extract any persistent facts "
    "about the user — their name, preferences, job, tools they use, habits, or anything "
    "they have explicitly shared about themselves.\n\n"
    "Return ONLY valid JSON in this exact format:\n"
    "{\"facts\": [{\"key\": \"snake_case_key\", \"value\": \"concise value\"}]}\n\n"
    "If there are no new facts, return {\"facts\": []}.\n"
    "Do NOT extract: current date/time, temporary state, greetings, or things the assistant said."
)


async def extract_and_store(
    user_text: str,
    assistant_text: str,
    ollama_client,
    memory,
    source: str = "",
):
    try:
        prompt = f"User: {user_text}\nAssistant: {assistant_text}"
        raw = await ollama_client.complete_simple(
            [{"role": "user", "content": prompt}], _SYSTEM
        )
        raw = raw.strip()
        # Strip markdown code fences some models add
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)
        facts = data.get("facts", [])
        for item in facts:
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            if key and value:
                await asyncio.to_thread(memory.upsert_fact, key, value, source)
                log.info("Fact stored: %s = %r", key, value)
        if facts:
            log.debug("Extracted %d fact(s)", len(facts))
    except Exception:
        log.debug("Fact extraction skipped (non-critical)", exc_info=True)
