import unittest

from navigation import navigation_handoffs, shaping_points
from routing import GeneratedRoute, RouteSegment


def route_with_points(points):
    route = GeneratedRoute()
    for index, (left, right) in enumerate(zip(points, points[1:]), 1):
        route.segments.append(RouteSegment(index, str(index), "secondary", 1000, 50, True, [left, right]))
        route.total_length_m += 1000
    return route


class NavigationTests(unittest.TestCase):
    def test_shaping_points_keep_endpoints_and_limit_count(self):
        route = route_with_points([(index * 0.01, 0) for index in range(20)])
        points = shaping_points(route, maximum=8)
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[-1], (0.19, 0.0))
        self.assertLessEqual(len(points), 8)

    def test_handoffs_encode_waypoints_and_waze_limitation(self):
        route = route_with_points([(0, 0), (0.1, 0.1), (0, 0)])
        links = navigation_handoffs(route)
        self.assertIn("waypoints", links["google_maps_url"])
        self.assertIn("waypoint=", links["apple_maps_url"])
        self.assertEqual(links["waze_label"], "Waze to first scenic stop")
        self.assertIn("navigate=yes", links["waze_url"])


if __name__ == "__main__":
    unittest.main()
