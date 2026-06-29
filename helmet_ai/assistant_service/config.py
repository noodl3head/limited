from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_ASSISTANT_DIR = Path(__file__).resolve().parent
load_dotenv(_ASSISTANT_DIR.parent / ".env.local")
load_dotenv(_ASSISTANT_DIR.parent / ".env")
load_dotenv(_ASSISTANT_DIR / ".env.local")
load_dotenv(_ASSISTANT_DIR / ".env")


@dataclass(frozen=True)
class AssistantConfig:
    agent_name: str = os.getenv("ASSISTANT_AGENT_NAME", "helmet-phone-first-agent")
    assistant_name: str = os.getenv("ASSISTANT_NAME", "MS Dhoni")
    initial_greeting: str = os.getenv("INITIAL_GREETING", "Haan bolo.")
    max_response_sentences: int = int(os.getenv("MAX_RESPONSE_SENTENCES", "2"))

    # Sarvam STT
    sarvam_stt_language: str = os.getenv("SARVAM_STT_LANGUAGE", "hi-IN")
    sarvam_stt_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    sarvam_stt_mode: str = os.getenv("SARVAM_STT_MODE", "codemix")

    # Sarvam TTS
    sarvam_tts_language: str = os.getenv("SARVAM_TTS_LANGUAGE", "hi-IN")
    sarvam_tts_model: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
    sarvam_tts_speaker: str = os.getenv("SARVAM_TTS_SPEAKER", "shubh")
    sarvam_tts_sample_rate: int = int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "24000"))

    # Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_router_model: str = os.getenv("GEMINI_ROUTER_MODEL", "gemini-2.5-flash-lite")
    gemini_enricher_model: str = os.getenv("GEMINI_ENRICHER_MODEL", "gemini-2.5-flash")
    gemini_composer_model: str = os.getenv("GEMINI_COMPOSER_MODEL", "gemini-2.5-flash")

    # Brave Search
    brave_api_key: str = os.getenv("BRAVE_API_KEY", "")
    brave_search_count: int = int(os.getenv("BRAVE_SEARCH_COUNT", "5"))
