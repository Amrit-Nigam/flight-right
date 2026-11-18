"""Bundled route metadata must produce identical inputs without network access."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from ml_pipeline.utils import route_features as routes


class RouteCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / "routes.json"
        self.shared.write_text(json.dumps({"routes": {"DEMO123": {"status": 200, "origin": "VABB", "destination": "OMDB"},
                                                       "UNKNOWN": {"status": 404}}}))
        self.enterContext(patch.object(routes, "ROUTES", self.root))
        self.enterContext(patch.dict(routes.os.environ, {"FLIGHT_RIGHT_ROUTE_CACHE": str(self.shared)}))
        routes._shared_routes.cache_clear()
        self.addCleanup(routes._shared_routes.cache_clear)

    def test_shared_positive_and_negative_do_not_fetch(self):
        with patch.object(routes.urllib.request, "urlopen", side_effect=AssertionError("unexpected network")):
            self.assertEqual(routes.route("demo123", fetch=True), ("VABB", "OMDB"))
            self.assertEqual(routes.route("UNKNOWN", fetch=True), (None, None))

    def test_missing_offline_route_stays_unknown(self):
        self.assertEqual(routes.route("ABSENT", fetch=False), (None, None))

    def test_local_cache_overrides_bundled_data(self):
        (self.root / "adsbdb").mkdir()
        (self.root / "adsbdb/DEMO123.json").write_text(json.dumps({"status": 200, "origin": "EGLL", "destination": "VABB"}))
        self.assertEqual(routes.route("DEMO123"), ("EGLL", "VABB"))

    def test_consolidation_preserves_all_route_feature_values(self):
        names = ["DEMO123", "UNKNOWN", "ABSENT"]
        airports = {"VABB": (19.09, 72.87), "OMDB": (25.25, 55.36)}
        with patch.object(routes, "airports", return_value=airports):
            bundled = routes.route_matrix(names, [20]*3, [70]*3, [280]*3)
            (self.root / "adsbdb").mkdir()
            for name, value in json.loads(self.shared.read_text())["routes"].items():
                (self.root / "adsbdb" / f"{name}.json").write_text(json.dumps(value))
            with patch.dict(routes.os.environ, {"FLIGHT_RIGHT_ROUTE_CACHE": ""}):
                individual = routes.route_matrix(names, [20]*3, [70]*3, [280]*3)
        np.testing.assert_array_equal(bundled, individual)


if __name__ == "__main__":
    unittest.main()
