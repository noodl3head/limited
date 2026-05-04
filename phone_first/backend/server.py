from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import uuid
from dataclasses import dataclass

from aiohttp import web
from livekit import api
from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
from livekit.protocol.room import CreateRoomRequest, ListParticipantsRequest

from backend.config import BackendConfig


logger = logging.getLogger("helmet-phone-first-backend")
logging.basicConfig(level=logging.INFO)

AGENT_NAME_ATTRIBUTE = "lk.agent.name"


@dataclass
class SessionRecord:
    session_id: str
    room_name: str
    participant_identity: str
    dispatch_id: str
    created_at: str


def _session_payload(
    *,
    config: BackendConfig,
    session: SessionRecord,
    participant_token: str | None,
    assistant_status: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "sessionId": session.session_id,
        "roomName": session.room_name,
        "livekitUrl": config.livekit_url,
        "assistantStatus": assistant_status,
    }
    if participant_token is not None:
        payload["participantToken"] = participant_token
    return payload


def _create_participant_token(
    config: BackendConfig, room_name: str, participant_identity: str
) -> str:
    ttl = dt.timedelta(minutes=config.session_token_ttl_minutes)
    return (
        api.AccessToken(config.livekit_api_key, config.livekit_api_secret)
        .with_identity(participant_identity)
        .with_name("Helmet Rider")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_ttl(ttl)
        .to_jwt()
    )


async def _get_assistant_status(
    config: BackendConfig, session: SessionRecord
) -> tuple[str, list[str]]:
    async with api.LiveKitAPI(
        config.livekit_url,
        config.livekit_api_key,
        config.livekit_api_secret,
    ) as lk_api:
        participants = await lk_api.room.list_participants(
            ListParticipantsRequest(room=session.room_name)
        )

    identities = [participant.identity for participant in participants.participants]
    assistant_connected = any(
        participant.attributes.get(AGENT_NAME_ATTRIBUTE) == config.assistant_agent_name
        for participant in participants.participants
    )
    return ("connected" if assistant_connected else "dispatched", identities)


async def create_session(request: web.Request) -> web.Response:
    config: BackendConfig = request.app["config"]
    sessions: dict[str, SessionRecord] = request.app["sessions"]
    try:
        body = await request.json() if request.can_read_body else {}
    except json.JSONDecodeError:
        body = {}

    session_id = uuid.uuid4().hex
    room_name = f"{config.room_prefix}-{session_id[:8]}"
    participant_identity = body.get("participantIdentity") or (
        f"{config.participant_prefix}-{session_id[:8]}"
    )

    async with api.LiveKitAPI(
        config.livekit_url,
        config.livekit_api_key,
        config.livekit_api_secret,
    ) as lk_api:
        await lk_api.room.create_room(
            CreateRoomRequest(
                name=room_name,
                empty_timeout=config.room_empty_timeout_seconds,
            )
        )
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=config.assistant_agent_name,
                room=room_name,
                metadata=json.dumps({"sessionId": session_id}),
            )
        )

    session = SessionRecord(
        session_id=session_id,
        room_name=room_name,
        participant_identity=participant_identity,
        dispatch_id=dispatch.id,
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    sessions[session_id] = session

    participant_token = _create_participant_token(config, room_name, participant_identity)
    payload = _session_payload(
        config=config,
        session=session,
        participant_token=participant_token,
        assistant_status="dispatched",
    )
    logger.info("Created session %s for room %s", session_id, room_name)
    return web.json_response(payload, status=201)


async def get_session(request: web.Request) -> web.Response:
    config: BackendConfig = request.app["config"]
    sessions: dict[str, SessionRecord] = request.app["sessions"]
    session_id = request.match_info["session_id"]
    session = sessions.get(session_id)
    if session is None:
        return web.json_response({"error": "Session not found"}, status=404)

    assistant_status, participant_identities = await _get_assistant_status(config, session)
    payload = _session_payload(
        config=config,
        session=session,
        participant_token=None,
        assistant_status=assistant_status,
    )
    payload["participants"] = participant_identities
    payload["dispatchId"] = session.dispatch_id
    payload["createdAt"] = session.created_at
    return web.json_response(payload)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def startup(app: web.Application) -> None:
    config: BackendConfig = app["config"]
    config.validate()
    logger.info(
        "Starting phone-first backend on %s:%s for agent %s",
        config.host,
        config.port,
        config.assistant_agent_name,
    )


async def cleanup(_: web.Application) -> None:
    await asyncio.sleep(0)


def create_app() -> web.Application:
    config = BackendConfig()
    app = web.Application()
    app["config"] = config
    app["sessions"] = {}
    app.router.add_get("/health", health)
    app.router.add_post("/sessions", create_session)
    app.router.add_get("/sessions/{session_id}", get_session)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    app = create_app()
    config: BackendConfig = app["config"]
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
