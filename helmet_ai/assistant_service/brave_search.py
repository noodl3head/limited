from __future__ import annotations

import aiohttp

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def brave_search(query: str, api_key: str, count: int = 5) -> list[dict]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": count,
        "search_lang": "en",
        "text_decorations": "0",
        "spellcheck": "1",
    }
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        response = await session.get(BRAVE_SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        data = await response.json(content_type=None)

    web = data.get("web", {}) if isinstance(data, dict) else {}
    results = web.get("results", []) if isinstance(web, dict) else []
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "description": r.get("description", ""),
        }
        for r in results
        if isinstance(r, dict)
    ]
