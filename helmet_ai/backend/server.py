from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import uuid
from dataclasses import asdict, dataclass

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


@dataclass
class LocationContext:
    latitude: float
    longitude: float
    accuracy_meters: float | None
    captured_at: str


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


def _normalize_session_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if len(normalized) < 8:
        return None
    return normalized[:8]


def _reconstruct_session_record(
    config: BackendConfig, session_id: str
) -> SessionRecord | None:
    session_key = _normalize_session_key(session_id)
    if session_key is None:
        return None

    return SessionRecord(
        session_id=session_id.strip().lower(),
        room_name=f"{config.room_prefix}-{session_key}",
        participant_identity=f"{config.participant_prefix}-{session_key}",
        dispatch_id="unknown",
        created_at="unknown",
    )


def _get_or_reconstruct_session(
    config: BackendConfig, sessions: dict[str, SessionRecord], session_id: str
) -> SessionRecord | None:
    session = sessions.get(session_id)
    if session is not None:
        return session
    return _reconstruct_session_record(config, session_id)


def _parse_location_payload(body: dict[str, object]) -> LocationContext:
    raw_location = body.get("location")
    if not isinstance(raw_location, dict):
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Expected location object"}),
            content_type="application/json",
        )

    try:
        latitude = float(raw_location["latitude"])
        longitude = float(raw_location["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Location must include numeric latitude and longitude"}),
            content_type="application/json",
        ) from exc

    accuracy = raw_location.get("accuracyMeters")
    accuracy_meters = float(accuracy) if isinstance(accuracy, (int, float, str)) and accuracy != "" else None
    captured_at = body.get("capturedAt")
    if not isinstance(captured_at, str) or not captured_at.strip():
        captured_at = dt.datetime.now(dt.timezone.utc).isoformat()

    return LocationContext(
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        captured_at=captured_at,
    )


async def create_session(request: web.Request) -> web.Response:
    config: BackendConfig = request.app["config"]
    sessions: dict[str, SessionRecord] = request.app["sessions"]
    try:
        body = await request.json() if request.can_read_body else {}
    except json.JSONDecodeError:
        body = {}

    session_id = uuid.uuid4().hex
    session_key = _normalize_session_key(session_id) or session_id[:8]
    room_name = f"{config.room_prefix}-{session_key}"
    participant_identity = body.get("participantIdentity") or (
        f"{config.participant_prefix}-{session_key}"
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
    session = _get_or_reconstruct_session(config, sessions, session_id)
    if session is None:
        return web.json_response({"error": "Session not found"}, status=404)

    if session.session_id not in sessions:
        logger.info(
            "Reconstructed stateless session %s for room %s",
            session.session_id,
            session.room_name,
        )

    try:
        assistant_status, participant_identities = await _get_assistant_status(config, session)
    except api.TwirpError as error:
        if error.code == "not_found":
            return web.json_response({"error": "Session not found"}, status=404)
        raise

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


async def update_session_context(request: web.Request) -> web.Response:
    config: BackendConfig = request.app["config"]
    location_contexts: dict[str, LocationContext] = request.app["location_contexts"]
    session_id = request.match_info["session_id"]
    session_key = _normalize_session_key(session_id)
    if session_key is None:
        return web.json_response({"error": "Session not found"}, status=404)

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Invalid JSON body"}),
            content_type="application/json",
        ) from exc

    location_context = _parse_location_payload(body)
    location_contexts[session_key] = location_context
    logger.info("Updated location context for session %s", session_key)
    return web.json_response({"ok": True, "sessionKey": session_key, "location": asdict(location_context)})


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
    app["location_contexts"] = {}
    app.router.add_get("/health", health)
    app.router.add_post("/sessions", create_session)
    app.router.add_get("/sessions/{session_id}", get_session)
    app.router.add_put("/sessions/{session_id}/context", update_session_context)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def main() -> None:
    app = create_app()
    config: BackendConfig = app["config"]
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
