from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp


GEOCODE_URL = "https://search.mappls.com/search/address/geocode"
ROUTE_URL_TEMPLATE = "https://route.mappls.com/route/direction/{resource}/{profile}/{origin};{destination}"


class MapplsError(RuntimeError):
    def __init__(self, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class GeocodedDestination:
    label: str
    latitude: float
    longitude: float

    @property
    def lon_lat(self) -> str:
        return f"{self.longitude:.6f},{self.latitude:.6f}"


@dataclass(frozen=True)
class DirectionsSummary:
    resolved_destination: str
    distance_km: float
    eta_minutes: int
    first_maneuver: str
    route_summary: str


async def geocode_destination(
    session: aiohttp.ClientSession, *, access_token: str, address: str
) -> GeocodedDestination:
    response = await session.get(
        GEOCODE_URL,
        params={
            "address": address,
            "itemCount": 1,
            "bias": 1,
            "access_token": access_token,
        },
    )
    payload = await _decode_response(response, "Mappls geocoding")
    item = _extract_first_geocode_result(payload)
    if item is None:
        raise MapplsError(f"I couldn't find a destination for '{address}'.", status=404)

    latitude, longitude = _extract_lat_lng(item)
    label = _extract_label(item, fallback=address)
    return GeocodedDestination(label=label, latitude=latitude, longitude=longitude)


async def compute_route(
    session: aiohttp.ClientSession,
    *,
    access_token: str,
    origin_latitude: float,
    origin_longitude: float,
    destination: GeocodedDestination,
    profile: str,
    resource: str,
) -> DirectionsSummary:
    origin = f"{origin_longitude:.6f},{origin_latitude:.6f}"
    route_url = ROUTE_URL_TEMPLATE.format(
        resource=resource,
        profile=profile,
        origin=origin,
        destination=destination.lon_lat,
    )
    response = await session.get(
        route_url,
        params={
            "steps": "true",
            "geometries": "polyline",
            "overview": "false",
            "access_token": access_token,
        },
    )
    payload = await _decode_response(response, "Mappls routing")
    routes = payload.get("routes") if isinstance(payload, dict) else None
    if not routes:
        raise MapplsError(
            f"I couldn't find a route to {destination.label}.",
            status=404,
        )

    route = routes[0]
    distance_m = _as_float(route.get("distance"))
    duration_s = _as_float(route.get("duration"))
    legs = route.get("legs") or []
    steps = legs[0].get("steps") if legs else []
    first_step = _pick_first_navigation_step(steps or [])
    first_maneuver = _render_maneuver(first_step)

    distance_km = round(distance_m / 1000, 1)
    eta_minutes = max(1, round(duration_s / 60))
    route_summary = f"{distance_km:.1f} km, about {eta_minutes} minutes."
    return DirectionsSummary(
        resolved_destination=destination.label,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
        first_maneuver=first_maneuver,
        route_summary=route_summary,
    )


async def _decode_response(response: aiohttp.ClientResponse, service_name: str) -> Any:
    if response.ok:
        return await response.json()

    text = await response.text()
    if response.status in (401, 403):
        raise MapplsError(
            f"{service_name} is not authorized. Check the Mappls key and product access.",
            status=502,
        )
    if response.status == 404:
        raise MapplsError(f"{service_name} could not find a matching result.", status=404)
    raise MapplsError(
        f"{service_name} failed with status {response.status}: {text[:200]}",
        status=502,
    )


def _extract_first_geocode_result(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, list):
        return payload[0] if payload else None
    if isinstance(payload, dict):
        for key in ("copResults", "results", "data", "suggestedLocations"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    return first
        if payload:
            return payload
    return None


def _extract_label(item: dict[str, Any], *, fallback: str) -> str:
    for key in (
        "placeName",
        "formatted_address",
        "formattedAddress",
        "address",
        "placeAddress",
        "poi",
        "eLoc",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _extract_lat_lng(item: dict[str, Any]) -> tuple[float, float]:
    latitude = item.get("latitude") or item.get("lat")
    longitude = item.get("longitude") or item.get("lng") or item.get("lon")
    if latitude is not None and longitude is not None:
        return _as_float(latitude), _as_float(longitude)

    mappls_pin = item.get("mapplsPin") or item.get("mappls_pin") or item.get("eLoc")
    if not mappls_pin:
        raise MapplsError("Mappls geocoding result did not include coordinates.", status=502)

    raise MapplsError(
        "Mappls geocoding returned a pin-only result without coordinates. "
        "Please use a more specific destination query.",
        status=409,
    )


def _pick_first_navigation_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not steps:
        return None

    for step in steps:
        maneuver = step.get("maneuver") or {}
        maneuver_type = str(maneuver.get("type") or "").lower()
        if maneuver_type and maneuver_type not in {"depart", "arrive"}:
            return step
    return steps[0]


def _render_maneuver(step: dict[str, Any] | None) -> str:
    if not step:
        return "Head toward the destination."

    maneuver = step.get("maneuver") or {}
    maneuver_type = str(maneuver.get("type") or "").lower()
    modifier = str(maneuver.get("modifier") or "").lower()
    road_name = str(step.get("name") or "").strip()

    base = {
        "depart": "Head out",
        "arrive": "You will arrive",
        "continue": "Continue",
        "merge": "Merge",
        "fork": "Keep",
        "off ramp": "Take the exit",
        "on ramp": "Take the ramp",
        "roundabout": "Enter the roundabout",
        "uturn": "Make a U-turn",
        "turn": "Turn",
    }.get(maneuver_type, "Continue")

    if maneuver_type in {"turn", "fork", "continue"} and modifier:
        if base == "Keep":
            base = f"Keep {modifier}"
        elif base == "Turn":
            base = f"Turn {modifier}"
        elif base == "Continue":
            base = f"Continue {modifier}"

    if road_name:
        if base.startswith("You will arrive"):
            return f"{base} at {road_name}."
        return f"{base} onto {road_name}."
    return f"{base}."


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MapplsError(f"Mappls returned an invalid numeric value: {value!r}", status=502) from exc
