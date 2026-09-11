"""Populate explainable road-elevation scores from a Valhalla height service.

This is an offline enrichment step. It samples each road, queries Valhalla's
``/height`` endpoint, and stores gain plus a 0-100 terrain-interest score.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from urllib import error, request

import psycopg2
import psycopg2.extras
from shapely import wkb as shapely_wkb
from shapely.geometry import LineString

logger = logging.getLogger("elevation")
SAMPLE_SPACING_M = 100.0
MAX_POINTS_PER_REQUEST = 500


def sample_line(line: LineString, length_m: float, spacing_m: float = SAMPLE_SPACING_M) -> list[tuple[float, float]]:
    if len(line.coords) < 2 or length_m <= 0:
        return []
    count = max(2, math.ceil(length_m / spacing_m) + 1)
    return [tuple(line.interpolate(index / (count - 1), normalized=True).coords[0]) for index in range(count)]


def elevation_metrics(heights: list[float | None], length_m: float) -> tuple[float, int]:
    """Return positive gain and a score rewarding climbing and terrain range."""
    usable = [float(value) for value in heights if value is not None]
    if len(usable) < 2 or length_m <= 0:
        return 0.0, 0
    gain = sum(max(0.0, current - previous) for previous, current in zip(usable, usable[1:]))
    elevation_range = max(usable) - min(usable)
    length_km = max(length_m / 1000.0, 0.1)
    score = round(min(100.0, (gain / length_km) * 1.4 + (elevation_range / length_km) * 0.8))
    return round(gain, 1), score


class ValhallaHeightClient:
    def __init__(self, base_url: str, timeout_seconds: float = 20.0):
        self.endpoint = f"{base_url.rstrip('/')}/height"
        self.timeout_seconds = timeout_seconds

    def heights(self, points: list[tuple[float, float]]) -> list[float | None]:
        payload = json.dumps({"shape": [{"lon": lon, "lat": lat} for lon, lat in points]}).encode()
        http_request = request.Request(self.endpoint, data=payload, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                result = json.load(response)
        except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Valhalla height request failed: {exc}") from exc
        heights = result.get("height")
        if not isinstance(heights, list) or len(heights) != len(points):
            raise RuntimeError("Valhalla returned an unexpected height response")
        return heights


UPSERT_SQL = """
    INSERT INTO road_scores (road_id, elevation_gain_m, elevation_score, computed_at)
    VALUES %s
    ON CONFLICT (road_id) DO UPDATE SET
        elevation_gain_m = EXCLUDED.elevation_gain_m,
        elevation_score = EXCLUDED.elevation_score,
        computed_at = EXCLUDED.computed_at
"""


def run(region: str, database_url: str, valhalla_url: str, write_batch: int = 500) -> None:
    client = ValhallaHeightClient(valhalla_url)
    with psycopg2.connect(database_url) as conn:
        with conn.cursor(name="elevation_roads") as read_cursor, conn.cursor() as write_cursor:
            read_cursor.itersize = write_batch
            read_cursor.execute("SELECT id, ST_AsBinary(geom), length_m FROM roads WHERE region = %s ORDER BY id", (region,))
            pending = []
            total = 0
            for road_id, geom_wkb, length_m in read_cursor:
                line = shapely_wkb.loads(bytes(geom_wkb))
                points = sample_line(line, length_m)
                if len(points) > MAX_POINTS_PER_REQUEST:
                    step = math.ceil(len(points) / MAX_POINTS_PER_REQUEST)
                    points = points[::step]
                    if points[-1] != tuple(line.coords[-1]):
                        points.append(tuple(line.coords[-1]))
                gain, score = elevation_metrics(client.heights(points), length_m)
                pending.append((road_id, gain, score))
                total += 1
                if len(pending) >= write_batch:
                    psycopg2.extras.execute_values(write_cursor, UPSERT_SQL, pending)
                    pending.clear()
                    logger.info("Elevation-scored %d roads...", total)
            if pending:
                psycopg2.extras.execute_values(write_cursor, UPSERT_SQL, pending)
    logger.info("Elevation scoring complete for %d roads in %s.", total, region)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--valhalla-url", default=os.environ.get("VALHALLA_URL", "http://localhost:8002"))
    args = parser.parse_args()
    if not args.database_url:
        sys.exit("Set DATABASE_URL or pass --database-url.")
    run(args.region, args.database_url, args.valhalla_url)


if __name__ == "__main__":
    main()
