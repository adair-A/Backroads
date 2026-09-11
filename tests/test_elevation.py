import unittest

from shapely.geometry import LineString

from elevation import elevation_metrics, sample_line


class ElevationTests(unittest.TestCase):
    def test_samples_include_both_ends(self):
        points = sample_line(LineString([(0, 0), (1, 0)]), 250, spacing_m=100)
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[-1], (1.0, 0.0))
        self.assertEqual(len(points), 4)

    def test_metrics_reward_gain_and_range(self):
        self.assertEqual(elevation_metrics([100, 100, 100], 1000), (0.0, 0))
        gain, score = elevation_metrics([100, 140, 120, 180], 1000)
        self.assertEqual(gain, 100)
        self.assertGreater(score, 0)

    def test_metrics_tolerate_missing_samples(self):
        gain, score = elevation_metrics([100, None, 130], 1000)
        self.assertEqual(gain, 30)
        self.assertGreater(score, 0)


if __name__ == "__main__":
    unittest.main()
