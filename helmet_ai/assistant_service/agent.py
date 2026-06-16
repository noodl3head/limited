from __future__ import annotations

import logging

from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions, WorkerOptions, llm
from livekit.plugins import sarvam, silero

try:
    from livekit.plugins import noise_cancellation
except ImportError:  # pragma: no cover - optional runtime dependency
    noise_cancellation = None

from assistant_service.backend_client import AssistantBackendClient, AssistantBackendError
from assistant_service.config import AssistantConfig


logger = logging.getLogger("helmet-phone-first-assistant")
logging.basicConfig(level=logging.INFO)

CONFIG = AssistantConfig()


class HelmetAssistant(Agent):
    def __init__(self, *, room_name: str) -> None:
        self._room_name = room_name
        self._backend_client = AssistantBackendClient(
            base_url=CONFIG.backend_base_url,
            assistant_backend_token=CONFIG.assistant_backend_token,
        )
        super().__init__(
            instructions=(
                f"You are {CONFIG.assistant_name}, a riding co-pilot. "
                "You can perfectly impersonate MS Dhoni, the Indian cricketer superstar. "
                "Prefer conversational, decisive phrasing. "
                "Respond only when the rider speaks. "
                f"Maximum {CONFIG.max_response_sentences} sentence(s). One is better. "
                "Always respond in English only. "
                "If the rider asks for directions, route guidance, ETA, or how far a destination is, "
                "call the get_directions tool. "
                "If the tool says location is unavailable, ask the rider to enable location or retry once the ride session has location access. "
                "If the tool returns a route, summarize it naturally with the destination, ETA, distance, and first maneuver. "
                "Never say: 'standing by', 'ready', 'let me know', 'anything else', 'on standby', or any variation. "
                "Silence is correct. Speak only when answering a direct input."
            )
        )

    @llm.function_tool
    async def get_directions(self, destination_query: str) -> dict[str, object]:
        """Get riding directions, ETA, and first maneuver for a destination."""
        destination_query = destination_query.strip()
        if not destination_query:
            return {
                "status": "error",
                "message": "No destination was provided.",
            }

        try:
            return await self._backend_client.get_directions(
                room_name=self._room_name,
                destination_query=destination_query,
            )
        except AssistantBackendError as error:
            return {
                "status": "error",
                "message": str(error),
            }


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
        agent=HelmetAssistant(room_name=ctx.room.name),
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
