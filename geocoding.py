"""Small, replaceable forward-geocoding boundary for address-first routing."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from urllib import error, parse, request


class GeocoderError(RuntimeError):
    pass


class NominatimGeocoder:
    """Policy-conscious Nominatim client with a bounded process-local cache."""

    def __init__(
        self,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "Backroads/1.0 (https://github.com/ixbh/Backroads)",
        timeout_seconds: float = 10,
        minimum_interval_seconds: float = 1,
        cache_size: int = 256,
    ):
        self.endpoint = f"{base_url.rstrip('/')}/search"
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self.cache_size = cache_size
        self._cache: OrderedDict[str, list[dict]] = OrderedDict()
        self._lock = threading.Lock()
        self._last_request_at = 0.0

    def search(self, query: str, limit: int = 5) -> list[dict]:
        normalized = " ".join(query.split()).casefold()
        if len(normalized) < 3:
            raise GeocoderError("Enter a more complete address.")
        with self._lock:
            cached = self._cache.get(normalized)
            if cached is not None:
                self._cache.move_to_end(normalized)
                return cached[:limit]
            remaining = self.minimum_interval_seconds - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
            params = parse.urlencode({
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "countrycodes": "us",
                "layer": "address",
                "limit": max(1, min(limit, 5)),
            })
            http_request = request.Request(
                f"{self.endpoint}?{params}",
                headers={"Accept": "application/json", "User-Agent": self.user_agent},
            )
            self._last_request_at = time.monotonic()
            try:
                with request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
            except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise GeocoderError("The address service is temporarily unavailable.") from exc
            matches = [
                {
                    "display_name": item.get("display_name", query),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "type": item.get("addresstype") or item.get("type"),
                }
                for item in payload
                if item.get("lat") is not None and item.get("lon") is not None
            ]
            self._cache[normalized] = matches
            self._cache.move_to_end(normalized)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return matches[:limit]
