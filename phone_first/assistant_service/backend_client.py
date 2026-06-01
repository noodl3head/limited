from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp


class AssistantBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssistantBackendClient:
    base_url: str
    assistant_backend_token: str

    async def get_directions(self, *, room_name: str, destination_query: str) -> dict[str, Any]:
        if not self.base_url:
            raise AssistantBackendError("Directions are unavailable because BACKEND_BASE_URL is missing.")
        if not self.assistant_backend_token:
            raise AssistantBackendError(
                "Directions are unavailable because ASSISTANT_BACKEND_TOKEN is missing."
            )

        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            response = await session.post(
                f"{self.base_url.rstrip('/')}/assistant/directions",
                headers={"X-Assistant-Token": self.assistant_backend_token},
                json={
                    "roomName": room_name,
                    "destinationQuery": destination_query,
                },
            )

            payload = await _decode_json(response)
            if response.ok:
                return payload

            message = str(payload.get("message") or payload.get("error") or "Directions failed.")
            raise AssistantBackendError(message)


async def _decode_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json()
    except aiohttp.ContentTypeError:
        payload = {"error": await response.text()}
    if not isinstance(payload, dict):
        return {"payload": payload}
    return payload
