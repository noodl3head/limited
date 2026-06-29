from __future__ import annotations

import asyncio
import logging

from livekit import agents, rtc
from livekit.agents import WorkerOptions
from livekit.agents.vad import VADEventType
from livekit.plugins import sarvam, silero

from assistant_service.config import AssistantConfig
from assistant_service.pipeline import run_pipeline

logger = logging.getLogger("helmet-assistant")
logging.basicConfig(level=logging.INFO)

CONFIG = AssistantConfig()


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

    stt = sarvam.STT(
        language=CONFIG.sarvam_stt_language,
        model=CONFIG.sarvam_stt_model,
        mode=CONFIG.sarvam_stt_mode,
    )
    tts = sarvam.TTS(
        target_language_code=CONFIG.sarvam_tts_language,
        model=CONFIG.sarvam_tts_model,
        speaker=CONFIG.sarvam_tts_speaker,
        speech_sample_rate=CONFIG.sarvam_tts_sample_rate,
        min_buffer_size=30,
        max_chunk_length=120,
    )

    # Audio source for TTS output — published as a local track in the room
    audio_source = rtc.AudioSource(CONFIG.sarvam_tts_sample_rate, 1)
    local_track = rtc.LocalAudioTrack.create_audio_track("assistant-audio", audio_source)

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    await ctx.room.local_participant.publish_track(
        local_track,
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
    )

    await _speak(tts, audio_source, CONFIG.initial_greeting)
    logger.info("Connected to room %s", ctx.room.name)

    participant = await ctx.wait_for_participant()
    logger.info("Participant joined: %s", participant.identity)

    audio_track = await _get_audio_track(ctx.room, participant)
    logger.info("Got audio track from participant %s", participant.identity)

    await _audio_loop(audio_track, vad=vad, stt=stt, tts=tts, audio_source=audio_source)


async def _get_audio_track(
    room: rtc.Room,
    participant: rtc.RemoteParticipant,
) -> rtc.Track:
    # Check already-subscribed tracks first
    for pub in participant.track_publications.values():
        if pub.track is not None and pub.kind == rtc.TrackKind.KIND_AUDIO:
            return pub.track

    loop = asyncio.get_event_loop()
    fut: asyncio.Future[rtc.Track] = loop.create_future()

    def _on_subscribed(
        track: rtc.Track,
        _: rtc.RemoteTrackPublication,
        p: rtc.RemoteParticipant,
    ) -> None:
        if p.identity == participant.identity and track.kind == rtc.TrackKind.KIND_AUDIO:
            if not fut.done():
                fut.set_result(track)

    room.on("track_subscribed", _on_subscribed)
    try:
        return await asyncio.wait_for(fut, timeout=30.0)
    finally:
        room.off("track_subscribed", _on_subscribed)


async def _audio_loop(
    track: rtc.Track,
    *,
    vad: silero.VAD,
    stt: sarvam.STT,
    tts: sarvam.TTS,
    audio_source: rtc.AudioSource,
) -> None:
    audio_stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
    vad_stream = vad.stream()

    # Feed audio frames into VAD concurrently
    async def _feed() -> None:
        async for audio_event in audio_stream:
            vad_stream.push_frame(audio_event.frame)

    asyncio.create_task(_feed())

    # One pipeline at a time; if already processing, drop the new utterance
    pipeline_lock = asyncio.Lock()

    async for vad_event in vad_stream:
        if vad_event.type != VADEventType.END_OF_SPEECH:
            continue

        frames = vad_event.frames
        if not frames:
            continue

        if pipeline_lock.locked():
            logger.debug("Pipeline busy, dropping utterance")
            continue

        asyncio.create_task(_handle_utterance(list(frames), pipeline_lock, stt, tts, audio_source))


async def _handle_utterance(
    frames: list,
    lock: asyncio.Lock,
    stt: sarvam.STT,
    tts: sarvam.TTS,
    audio_source: rtc.AudioSource,
) -> None:
    async with lock:
        # STT
        try:
            stt_event = await stt.recognize(frames)
        except Exception as exc:
            logger.error("STT error: %s", exc)
            return

        if not stt_event.alternatives:
            return
        transcript = stt_event.alternatives[0].text.strip()
        if not transcript:
            return

        logger.info("Transcript: %s", transcript)

        # Pipeline
        try:
            response_text = await run_pipeline(transcript, CONFIG)
        except Exception as exc:
            logger.error("Pipeline error: %s", exc)
            response_text = "Bhai, kuch gadbad ho gayi. Phir poochho."

        logger.info("Response: %s", response_text)

        # TTS
        await _speak(tts, audio_source, response_text)


async def _speak(tts: sarvam.TTS, audio_source: rtc.AudioSource, text: str) -> None:
    try:
        stream = tts.synthesize(text)
        async for chunk in stream:
            frame = getattr(chunk, "frame", None)
            if frame is not None:
                await audio_source.capture_frame(frame)
    except Exception as exc:
        logger.error("TTS error: %s", exc)


def run() -> None:
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name=CONFIG.agent_name,
        )
    )
