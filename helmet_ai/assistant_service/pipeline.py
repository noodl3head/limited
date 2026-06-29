from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from assistant_service.brave_search import brave_search

if TYPE_CHECKING:
    from assistant_service.config import AssistantConfig

logger = logging.getLogger("helmet-pipeline")

_DHONI_SYSTEM = (
"You are MS Dhoni — the cricketer, captain, finisher. You're now a voice in a smart helmet."
"How Dhoni speaks:"
"- Short sentences. Never more than two."
"- Calm even when the information is bad. Haan, traffic hai. Aur kya."
"- Occasionally uses cricket as a frame for life. Naturally, not forced."
"- Understated. If something is impressive, he says thoda acha tha."
"- Uses bhai/yaar once per answer, never twice. This is not a compulsion, it should feel natural."
"- Never explains himself, unless asked to. States. Moves on."
"- Ranchi Hindi. Simple words. No fancy vocabulary."
"Examples:"
"Q: Kaun jita IPL mein?"
"A: Chennai ne. Wahi hona tha."
"Q: Weather kaisa hai aage?"
"A: Baarish aayegi. Helmet already hai, toh koi baat nahi."
"Q: Best route kaunsa hai?"
"A: Ye lo — 12 km, 20 minute. Seedha niklo."
"Respond in this voice. 1-2 sentences max. Never break character."
)


async def run_pipeline(transcript: str, config: AssistantConfig) -> str:
    client = genai.Client(api_key=config.gemini_api_key)

    route = await _route(client, config.gemini_router_model, transcript)
    logger.info("Route decision: %s", route)

    if route == "device":
        return await _direct_answer(client, config.gemini_composer_model, transcript)

    search_query = await _enrich(client, config.gemini_enricher_model, transcript)
    logger.info("Enriched search query: %s", search_query)

    try:
        results = await brave_search(search_query, config.brave_api_key, config.brave_search_count)
    except Exception as exc:
        logger.warning("Brave search failed (%s), falling back to direct answer", exc)
        return await _direct_answer(client, config.gemini_composer_model, transcript)

    if not results:
        logger.info("No search results, falling back to direct answer")
        return await _direct_answer(client, config.gemini_composer_model, transcript)

    context = await _validate(client, config.gemini_router_model, transcript, results)
    logger.info("Validated context: %s", context[:120])

    return await _compose(client, config.gemini_composer_model, transcript, context)


async def _route(client: genai.Client, model: str, transcript: str) -> str:
    prompt = (
        "Classify this motorcycle rider's spoken Hinglish query.\n"
        "Reply with ONLY the word: search  OR  device\n\n"
        "search = needs live or current information from the web "
        "(news, scores, weather, prices, current events, latest anything)\n"
        "device = can be answered directly from general knowledge "
        "(definitions, history, math, simple facts, things that don't change)\n\n"
        f"Query: {transcript}"
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=5, temperature=0.0),
    )
    text = (response.text or "").strip().lower()
    return "search" if "search" in text else "device"


async def _enrich(client: genai.Client, model: str, transcript: str) -> str:
    prompt = (
        "Convert this spoken Hinglish query from a motorcycle rider into a concise, "
        "effective English web search query. Remove filler words. Be specific. "
        "Return only the search query, nothing else.\n\n"
        f"Query: {transcript}"
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=40, temperature=0.1),
    )
    enriched = (response.text or "").strip()
    return enriched if enriched else transcript


async def _validate(
    client: genai.Client,
    model: str,
    transcript: str,
    results: list[dict],
) -> str:
    snippets = "\n".join(
        f"- {r['title']}: {r['description']}"
        for r in results[:5]
        if r.get("title") or r.get("description")
    )
    prompt = (
        f"User asked: {transcript}\n\n"
        f"Search results:\n{snippets}\n\n"
        "Extract the 2-3 most relevant facts that directly answer the user's question. "
        "Be factual and concise. No commentary, no labels."
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=150, temperature=0.1),
    )
    return (response.text or "").strip()


async def _compose(
    client: genai.Client,
    model: str,
    transcript: str,
    context: str,
) -> str:
    prompt = f"Question: {transcript}\nFacts: {context}"
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_DHONI_SYSTEM,
            max_output_tokens=120,
            temperature=0.8,
        ),
    )
    return (response.text or "Kuch nahi mila, bhai.").strip()


async def _direct_answer(client: genai.Client, model: str, transcript: str) -> str:
    response = await client.aio.models.generate_content(
        model=model,
        contents=transcript,
        config=types.GenerateContentConfig(
            system_instruction=_DHONI_SYSTEM,
            max_output_tokens=120,
            temperature=0.8,
        ),
    )
    return (response.text or "Hmm, nahi pata yaar.").strip()
