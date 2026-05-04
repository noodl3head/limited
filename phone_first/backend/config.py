from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(_BACKEND_DIR / ".env.local")
load_dotenv(_BACKEND_DIR / ".env")


@dataclass(frozen=True)
class BackendConfig:
    livekit_url: str = os.getenv("LIVEKIT_URL", "")
    livekit_api_key: str = os.getenv("LIVEKIT_API_KEY", "")
    livekit_api_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
    host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", os.getenv("BACKEND_PORT", "8080")))
    room_prefix: str = os.getenv("ROOM_PREFIX", "helmet-session")
    participant_prefix: str = os.getenv("PARTICIPANT_PREFIX", "helmet-rider")
    assistant_agent_name: str = os.getenv("ASSISTANT_AGENT_NAME", "helmet-phone-first-agent")
    session_token_ttl_minutes: int = int(os.getenv("SESSION_TOKEN_TTL_MINUTES", "60"))
    room_empty_timeout_seconds: int = int(os.getenv("ROOM_EMPTY_TIMEOUT_SECONDS", "600"))

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("LIVEKIT_URL", self.livekit_url),
                ("LIVEKIT_API_KEY", self.livekit_api_key),
                ("LIVEKIT_API_SECRET", self.livekit_api_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing backend configuration: {', '.join(missing)}")
