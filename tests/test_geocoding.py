import io
import json
import unittest
from unittest.mock import patch

from geocoding import NominatimGeocoder


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): return False


class GeocodingTests(unittest.TestCase):
    def test_search_normalizes_results_and_caches_repeated_address(self):
        payload = [{
            "display_name": "123 Main Street, Minneapolis, Minnesota",
            "lat": "44.98", "lon": "-93.27", "addresstype": "house",
        }]
        geocoder = NominatimGeocoder(minimum_interval_seconds=0)
        with patch("geocoding.request.urlopen", return_value=FakeResponse(json.dumps(payload).encode())) as opened:
            first = geocoder.search("123 Main Street, Minneapolis")
            second = geocoder.search("  123   MAIN street, Minneapolis ")
        self.assertEqual(first[0]["lat"], 44.98)
        self.assertEqual(first, second)
        opened.assert_called_once()
        sent = opened.call_args.args[0]
        self.assertIn("countrycodes=us", sent.full_url)
        self.assertIn("Backroads/1.0", sent.headers["User-agent"])


if __name__ == "__main__":
    unittest.main()
