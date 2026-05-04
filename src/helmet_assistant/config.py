from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv(".env.local")


@dataclass(frozen=True)
class AssistantConfig:
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-4.1-mini")
    assistant_name: str = os.getenv("ASSISTANT_NAME", "MS Dhoni")
    initial_greeting: str = os.getenv(
        "INITIAL_GREETING",
        "Hello! I'm MS DHONI. Press and speak when you're ready.",
    )
    max_response_sentences: int = int(os.getenv("MAX_RESPONSE_SENTENCES", "5"))
    sarvam_stt_language: str = os.getenv("SARVAM_STT_LANGUAGE", "en-IN")
    sarvam_stt_model: str = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    sarvam_stt_mode: str = os.getenv("SARVAM_STT_MODE", "transcribe")
    sarvam_tts_language: str = os.getenv("SARVAM_TTS_LANGUAGE", "en-IN")
    sarvam_tts_model: str = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
    sarvam_tts_speaker: str = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
    sarvam_tts_sample_rate: int = int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "24000"))
