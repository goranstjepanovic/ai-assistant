import asyncio
import json
import logging

log = logging.getLogger(__name__)

_SYSTEM = (
    "You are an information extractor. Given a short conversation exchange, extract two types of information.\n\n"
    "1. USER FACTS: persistent facts about the user — their name, job, preferences, tools, habits, "
    "or anything they have explicitly shared about themselves.\n\n"
    "2. RELATIONSHIP SIGNALS: observations about how this user prefers to interact with the assistant — "
    "do they want brief or detailed answers, did humor land or fall flat, do they use the assistant's name, "
    "are they formal or casual, do they seem to appreciate directness, did they react positively or "
    "negatively to the assistant's tone. Only extract signals you can clearly infer.\n\n"
    "Return ONLY valid JSON:\n"
    "{\"facts\": [{\"key\": \"snake_case_key\", \"value\": \"concise value\"}], "
    "\"signals\": [{\"key\": \"rel_snake_case\", \"value\": \"concise observation\"}]}\n\n"
    "Signal keys MUST start with 'rel_'. Examples: rel_preferred_name, rel_prefers_brief, "
    "rel_humor_receptive, rel_register, rel_uses_assistant_name.\n"
    "If there is nothing to extract for a category, return an empty list for that key.\n"
    "Do NOT extract: current date/time, temporary state, or things only the assistant said.\n"
    "Do NOT duplicate a fact as a signal or vice versa."
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
            if key and value and not key.startswith("rel_"):
                await asyncio.to_thread(memory.upsert_fact, key, value, source)
                log.info("Fact stored: %s = %r", key, value)

        signals = data.get("signals", [])
        for item in signals:
            key = str(item.get("key", "")).strip()
            value = str(item.get("value", "")).strip()
            if key.startswith("rel_") and value:
                await asyncio.to_thread(memory.upsert_fact, key, value, source)
                log.info("Relationship signal stored: %s = %r", key, value)

        total = len(facts) + len(signals)
        if total:
            log.debug("Extracted %d fact(s), %d signal(s)", len(facts), len(signals))
    except Exception:
        log.debug("Fact extraction skipped (non-critical)", exc_info=True)
