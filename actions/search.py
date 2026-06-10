import asyncio
import logging

log = logging.getLogger(__name__)


def _web_search(query: str, max_results: int = 5) -> str:
    from ddgs import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))

    if not results:
        return f"No results found for: {query}"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "").strip()
        url = r.get("href", "").strip()
        snippet = r.get("body", "").strip()
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}")

    log.info("web_search %r -> %d results", query, len(results))
    return "\n\n".join(lines)


async def web_search_async(query: str, max_results: int = 5) -> str:
    return await asyncio.to_thread(_web_search, query, max_results)
