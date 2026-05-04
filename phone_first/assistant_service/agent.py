from __future__ import annotations

import logging

from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, WorkerOptions
from livekit.plugins import sarvam, silero

try:
    from livekit.plugins import noise_cancellation
except ImportError:  # pragma: no cover - optional runtime dependency
    noise_cancellation = None

from assistant_service.config import AssistantConfig


logger = logging.getLogger("helmet-phone-first-assistant")
logging.basicConfig(level=logging.INFO)

CONFIG = AssistantConfig()


class HelmetAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                f"You are {CONFIG.assistant_name}, a riding co-pilot. "
                "You can perfectly impersonate MS Dhoni. "
                "Personify the calm, composed, practical, pressure-proof presence of MS Dhoni. "
                "Sound grounded, economical, confident, and tactically sharp. "
                "Prefer conversational, decisive phrasing with a cool head under pressure. "
                "Respond only when the rider speaks. "
                f"Maximum {CONFIG.max_response_sentences} sentence(s). One is better. "
                "Always respond in English only. "
                "Never say: 'standing by', 'ready', 'let me know', 'anything else', 'on standby', or any variation. "
                "Silence is correct. Speak only when answering a direct input."
                "Use *you know* as a filler, like how MS Dhoni uses it while speaking. Do not spam this. Use this naturally. "
            )
        )


def prewarm(proc: agents.JobProcess) -> None:
    logger.info("Prewarming Silero VAD")
    proc.userdata["vad"] = silero.VAD.load(
        min_speech_duration=0.10,
        min_silence_duration=0.15,
        prefix_padding_duration=0.20,
        sample_rate=16000,
    )


async def entrypoint(ctx: agents.JobContext) -> None:
    vad: silero.VAD = ctx.proc.userdata["vad"]

    session = AgentSession(
        vad=vad,
        llm=CONFIG.llm_model,
        stt=sarvam.STT(
            language=CONFIG.sarvam_stt_language,
            model=CONFIG.sarvam_stt_model,
            mode=CONFIG.sarvam_stt_mode,
        ),
        tts=sarvam.TTS(
            target_language_code=CONFIG.sarvam_tts_language,
            model=CONFIG.sarvam_tts_model,
            speaker=CONFIG.sarvam_tts_speaker,
            speech_sample_rate=CONFIG.sarvam_tts_sample_rate,
            min_buffer_size=30,
            max_chunk_length=120,
        ),
    )

    logger.info("Connecting to room %s", ctx.room.name)
    room_input_options = RoomInputOptions(
        noise_cancellation=noise_cancellation.BVC() if noise_cancellation else None,
    )

    if noise_cancellation is None:
        logger.warning("Noise cancellation plugin is not installed; continuing without it")

    await session.start(
        room=ctx.room,
        agent=HelmetAssistant(),
        room_input_options=room_input_options,
    )

    await session.generate_reply(
        instructions=CONFIG.initial_greeting,
    )


def run() -> None:
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=CONFIG.agent_name,
        )
    )
