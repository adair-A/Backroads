"""Navigation handoff helpers for generated Backroads routes."""

from __future__ import annotations

import math
from urllib.parse import urlencode


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon, dlat = lon2 - lon1, lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def route_coordinates(route) -> list[tuple[float, float]]:
    coordinates = []
    for segment in route.segments:
        for coordinate in segment.coords:
            point = (float(coordinate[0]), float(coordinate[1]))
            if not coordinates or point != coordinates[-1]:
                coordinates.append(point)
    return coordinates


def shaping_points(route, maximum: int = 10) -> list[tuple[float, float]]:
    """Select distance-spaced points, always retaining route endpoints."""
    coordinates = route_coordinates(route)
    if len(coordinates) <= maximum:
        return coordinates
    cumulative = [0.0]
    for left, right in zip(coordinates, coordinates[1:]):
        cumulative.append(cumulative[-1] + _haversine_m(left, right))
    total = cumulative[-1]
    if total <= 0:
        return [coordinates[0], coordinates[-1]]
    selected = []
    cursor = 0
    for index in range(maximum):
        target = total * index / (maximum - 1)
        while cursor + 1 < len(cumulative) and cumulative[cursor] < target:
            cursor += 1
        selected.append(coordinates[cursor])
    return list(dict.fromkeys(selected))


def navigation_handoffs(route) -> dict:
    points = shaping_points(route)
    if len(points) < 2:
        return {}
    origin, destination = points[0], points[-1]
    intermediate = points[1:-1]
    coordinate = lambda point: f"{point[1]:.6f},{point[0]:.6f}"
    google_params = {
        "api": "1",
        "origin": coordinate(origin),
        "destination": coordinate(destination),
        "travelmode": "driving",
    }
    if intermediate:
        google_params["waypoints"] = "|".join(coordinate(point) for point in intermediate)
    apple_pairs = [
        ("source", coordinate(origin)),
        ("destination", coordinate(destination)),
        *(('waypoint', coordinate(point)) for point in intermediate),
        ("mode", "driving"),
    ]
    # A loop's final destination is its start, which gives Waze no route-shape
    # information. Send it to the first scenic shaping point and label this
    # limitation explicitly in the UI.
    waze_target = intermediate[0] if intermediate else destination
    return {
        "google_maps_url": "https://www.google.com/maps/dir/?" + urlencode(google_params),
        "apple_maps_url": "https://maps.apple.com/directions?" + urlencode(apple_pairs),
        "waze_url": "https://waze.com/ul?" + urlencode({"ll": coordinate(waze_target), "navigate": "yes", "utm_source": "backroads"}),
        "waze_label": "Waze to first scenic stop" if intermediate else "Open in Waze",
        "shaping_point_count": len(points),
    }
