"""Navigation-grade routing provider boundary.

Backroads remains responsible for scenic candidate selection. Providers turn a
small set of shaping points into a legal path with maneuver instructions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from navigation import shaping_points


class RoutingProviderError(RuntimeError):
    pass


def decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    """Decode Valhalla's six-decimal encoded polyline into (lon, lat)."""
    coordinates = []
    index = latitude = longitude = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            result = shift = 0
            while True:
                if index >= len(encoded):
                    raise RoutingProviderError("Truncated encoded route shape")
                value = ord(encoded[index]) - 63
                index += 1
                result |= (value & 0x1F) << shift
                shift += 5
                if value < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += deltas[0]
        longitude += deltas[1]
        coordinates.append((longitude / 1_000_000.0, latitude / 1_000_000.0))
    return coordinates


@dataclass(slots=True)
class ValidatedRoute:
    coordinates: list[tuple[float, float]]
    maneuvers: list[dict]
    distance_mi: float
    duration_seconds: int
    provider: str = "valhalla"

    def to_dict(self) -> dict:
        return {
            "status": "validated",
            "provider": self.provider,
            "distance_mi": round(self.distance_mi, 2),
            "duration_seconds": self.duration_seconds,
            "maneuvers": self.maneuvers,
            "geojson": {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "properties": {"provider": self.provider, "navigation_validated": True},
                    "geometry": {"type": "LineString", "coordinates": self.coordinates},
                }],
            },
        }


class ValhallaRoutingProvider:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0):
        self.endpoint = f"{base_url.rstrip('/')}/route"
        self.timeout_seconds = timeout_seconds

    def validate(self, route, maximum_shaping_points: int = 20) -> ValidatedRoute:
        points = shaping_points(route, maximum=maximum_shaping_points)
        if len(points) < 2:
            raise RoutingProviderError("Route has too little geometry to validate")
        locations = []
        for index, (lon, lat) in enumerate(points):
            locations.append({
                "lon": lon,
                "lat": lat,
                "type": "break" if index in (0, len(points) - 1) else "via",
                "radius": 75,
            })
        payload = json.dumps({
            "locations": locations,
            "costing": "auto",
            "units": "miles",
            "directions_options": {"units": "miles", "language": "en-US"},
        }).encode()
        http_request = request.Request(
            self.endpoint, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Backroads/1.0"},
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                result = json.load(response)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RoutingProviderError(f"Valhalla route request failed: {exc}") from exc
        trip = result.get("trip") or {}
        if trip.get("status", 0) not in (0, None):
            raise RoutingProviderError(trip.get("status_message") or "Valhalla rejected the route")
        legs = trip.get("legs") or []
        coordinates = []
        maneuvers = []
        for leg_index, leg in enumerate(legs):
            decoded = decode_polyline6(leg.get("shape", ""))
            if coordinates and decoded and coordinates[-1] == decoded[0]:
                decoded = decoded[1:]
            coordinates.extend(decoded)
            for maneuver in leg.get("maneuvers") or []:
                maneuvers.append({
                    "leg": leg_index,
                    "instruction": maneuver.get("instruction"),
                    "verbal_instruction": maneuver.get("verbal_post_transition_instruction")
                        or maneuver.get("verbal_pre_transition_instruction"),
                    "length_mi": maneuver.get("length"),
                    "time_seconds": maneuver.get("time"),
                    "type": maneuver.get("type"),
                })
        summary = trip.get("summary") or {}
        if len(coordinates) < 2:
            raise RoutingProviderError("Valhalla returned no usable route geometry")
        return ValidatedRoute(
            coordinates=coordinates,
            maneuvers=maneuvers,
            distance_mi=float(summary.get("length") or 0),
            duration_seconds=round(float(summary.get("time") or 0)),
        )
