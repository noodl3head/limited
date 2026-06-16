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
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")
    backend_base_url: str = os.getenv("BACKEND_BASE_URL", "")
    assistant_backend_token: str = os.getenv("ASSISTANT_BACKEND_TOKEN", "")
    assistant_name: str = os.getenv("ASSISTANT_NAME", "MS Dhoni")
    initial_greeting: str = os.getenv(
        "INITIAL_GREETING",
        "Hello! I'm MS DHONI. Press and speak when you're ready.",
    )
    max_response_sentences: int = int(os.getenv("MAX_RESPONSE_SENTENCES", "6"))
    sarvam_stt_language: str = os.getenv("SARVAM_STT_LANGUAGE", "en-IN")
    sarvam_stt_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    sarvam_stt_mode: str = os.getenv("SARVAM_STT_MODE", "transcribe")
    sarvam_tts_language: str = os.getenv("SARVAM_TTS_LANGUAGE", "en-IN")
    sarvam_tts_model: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
    sarvam_tts_speaker: str = os.getenv("SARVAM_TTS_SPEAKER", "shubh")
    sarvam_tts_sample_rate: int = int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "24000"))
