import json
import unittest
from unittest.mock import patch

from routing import GeneratedRoute, RouteSegment
from routing_provider import ValhallaRoutingProvider, decode_polyline6


def encode_polyline6(points):
    output = []
    previous_lat = previous_lon = 0
    for lon, lat in points:
        values = [round(lat * 1_000_000) - previous_lat, round(lon * 1_000_000) - previous_lon]
        previous_lat += values[0]
        previous_lon += values[1]
        for value in values:
            value = ~(value << 1) if value < 0 else value << 1
            while value >= 0x20:
                output.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            output.append(chr(value + 63))
    return "".join(output)


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self, *_): return json.dumps(self.payload).encode()


class RoutingProviderTests(unittest.TestCase):
    def test_polyline6_round_trip(self):
        points = [(-93.265, 44.9778), (-93.25, 44.99), (-93.2, 45.01)]
        decoded = decode_polyline6(encode_polyline6(points))
        self.assertEqual(decoded, points)

    def test_valhalla_provider_extracts_geometry_and_maneuvers(self):
        points = [(-93.265, 44.9778), (-93.25, 44.99)]
        route = GeneratedRoute([
            RouteSegment(1, "Road", "secondary", 1000, 50, True, points)
        ], 1000)
        payload = {"trip": {"status": 0, "summary": {"length": 1.2, "time": 180}, "legs": [{
            "shape": encode_polyline6(points),
            "maneuvers": [{"instruction": "Turn right", "length": 0.2, "time": 30, "type": 10}],
        }]}}
        with patch("routing_provider.request.urlopen", return_value=FakeResponse(payload)) as opened:
            result = ValhallaRoutingProvider("http://valhalla.test").validate(route)
        self.assertEqual(result.coordinates, points)
        self.assertEqual(result.maneuvers[0]["instruction"], "Turn right")
        self.assertEqual(result.distance_mi, 1.2)
        sent = json.loads(opened.call_args.args[0].data)
        self.assertEqual(sent["locations"][0]["type"], "break")
        self.assertEqual(sent["locations"][-1]["type"], "break")


if __name__ == "__main__":
    unittest.main()
