from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from typing import TYPE_CHECKING

from google import genai
from google.genai import types

from assistant_service.brave_search import brave_search

if TYPE_CHECKING:
    from assistant_service.config import AssistantConfig

logger = logging.getLogger("helmet-pipeline")

_gemini_client: genai.Client | None = None


def _get_client(api_key: str) -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client

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

# Known device actions the assistant can classify.
# Execution is BluArmor's responsibility — we only identify intent.
_DEVICE_ACTIONS = (
    "play_music, pause_music, next_track, previous_track, "
    "call, answer_call, end_call, reject_call, "
    "volume_up, volume_down, mute, "
    "navigate"
)


@dataclasses.dataclass
class Turn:
    transcript: str
    response: str


@dataclasses.dataclass
class PipelineResult:
    text: str
    route: str
    device_intent: dict | None = None


async def run_pipeline(
    transcript: str,
    config: AssistantConfig,
    memory: list[Turn],
) -> PipelineResult:
    client = _get_client(config.gemini_api_key)
    context = _format_memory(memory)

    # Router and enricher run in parallel — if route is "search" the query
    # is already enriched by the time we need it, saving ~0.5–1s.
    route, enriched_query = await asyncio.gather(
        _route(client, config.gemini_router_model, transcript, context),
        _enrich(client, config.gemini_enricher_model, transcript),
    )
    logger.info("Route: %s | Enriched: %s", route, enriched_query)

    if route == "device":
        return await _handle_device(client, config, transcript, context)

    if route == "search":
        result = await _handle_search(client, config, transcript, context, enriched_query)
        if result is not None:
            return result
        # search failed or no results — fall through to chat

    text = await _direct_answer(client, config.gemini_composer_model, transcript, context)
    return PipelineResult(text=text, route="chat")


# ── Route handlers ────────────────────────────────────────────────────────────

async def _handle_device(
    client: genai.Client,
    config: AssistantConfig,
    transcript: str,
    context: str,
) -> PipelineResult:
    intent = await _extract_device_intent(client, config.gemini_router_model, transcript)
    ack = await _device_ack(client, config.gemini_composer_model, transcript, intent, context)
    logger.info("Device intent: %s", intent)
    return PipelineResult(text=ack, route="device", device_intent=intent)


async def _handle_search(
    client: genai.Client,
    config: AssistantConfig,
    transcript: str,
    context: str,
    enriched_query: str,
) -> PipelineResult | None:
    try:
        results = await brave_search(enriched_query, config.brave_api_key, config.brave_search_count)
    except Exception as exc:
        logger.warning("Brave search failed (%s), falling back to chat", exc)
        return None

    if not results:
        logger.info("No search results, falling back to chat")
        return None

    facts = await _validate(client, config.gemini_router_model, transcript, results)
    logger.info("Validated context: %s", facts[:120])

    text = await _compose(client, config.gemini_composer_model, transcript, facts, context)
    return PipelineResult(text=text, route="search")


# ── Gemini calls ──────────────────────────────────────────────────────────────

async def _route(
    client: genai.Client, model: str, transcript: str, context: str
) -> str:
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    prompt = (
        f"{context_block}"
        "Classify this motorcycle rider's Hinglish query.\n"
        "Reply with ONLY one word: search  OR  chat  OR  device\n\n"
        "search = needs live web data (news, scores, weather, prices, current events)\n"
        "chat   = answer from knowledge or continue the conversation "
        "(facts, reactions, opinions, follow-ups, anything not needing the web)\n"
        "device = phone or hardware control "
        f"({_DEVICE_ACTIONS})\n\n"
        f"Query: {transcript}"
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=5, temperature=0.0),
    )
    text = (response.text or "").strip().lower()
    if "device" in text:
        return "device"
    if "search" in text:
        return "search"
    return "chat"


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
    facts: str,
    context: str,
) -> str:
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    prompt = f"{context_block}Question: {transcript}\nFacts: {facts}"
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_DHONI_SYSTEM,
            max_output_tokens=120,
            temperature=0.8,
        ),
    )
    return (response.text or "Kuch nahi mila.").strip()


async def _direct_answer(
    client: genai.Client, model: str, transcript: str, context: str
) -> str:
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    prompt = f"{context_block}Current: {transcript}"
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_DHONI_SYSTEM,
            max_output_tokens=120,
            temperature=0.8,
        ),
    )
    return (response.text or "Hmm, nahi pata.").strip()


async def _extract_device_intent(
    client: genai.Client, model: str, transcript: str
) -> dict:
    prompt = (
        "Extract the device action from this query. Return valid JSON only, no explanation.\n"
        f"Available actions: {_DEVICE_ACTIONS}\n\n"
        "Examples:\n"
        "'Play Shape of You' → {\"action\": \"play_music\", \"query\": \"Shape of You\"}\n"
        "'Call Mom' → {\"action\": \"call\", \"contact\": \"Mom\"}\n"
        "'Answer the call' → {\"action\": \"answer_call\"}\n"
        "'Volume up' → {\"action\": \"volume_up\"}\n\n"
        f"Query: {transcript}\n"
        "JSON:"
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=60, temperature=0.0),
    )
    raw = (response.text or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "unknown", "raw": transcript}


async def _device_ack(
    client: genai.Client,
    model: str,
    transcript: str,
    intent: dict,
    context: str,
) -> str:
    action = intent.get("action", "unknown")
    context_block = f"Recent conversation:\n{context}\n\n" if context else ""
    prompt = (
        f"{context_block}"
        f"The rider said: {transcript}\n"
        f"Action identified: {action}\n"
        "Give a very brief natural acknowledgement in Dhoni's voice. "
        "Do not say you will do it — BluArmor will handle execution. Just acknowledge."
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_DHONI_SYSTEM,
            max_output_tokens=40,
            temperature=0.7,
        ),
    )
    return (response.text or "Haan.").strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_memory(memory: list[Turn]) -> str:
    if not memory:
        return ""
    lines = []
    for turn in memory[-3:]:
        lines.append(f"Rider: {turn.transcript}")
        lines.append(f"Dhoni: {turn.response}")
    return "\n".join(lines)
