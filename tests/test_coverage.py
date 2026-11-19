"""Coverage model on a synthetic plan: the fit must recover a known path-loss exponent and wall loss."""

import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from agent.device import coverage as cv


def synthetic_plan(folder: Path) -> Path:
    """Two rows of rooms (600 x 400 px, 2 cm per px): a router room top left, walls 6 px thick, door gaps."""
    img = Image.new("RGB", (640, 440), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 620, 420], fill=(225, 200, 160))
    wall = (0, 0, 0)
    d.rectangle([20, 20, 620, 26], fill=wall)
    d.rectangle([20, 414, 620, 420], fill=wall)
    d.rectangle([20, 20, 26, 420], fill=wall)
    d.rectangle([614, 20, 620, 420], fill=wall)
    d.rectangle([220, 20, 226, 180], fill=wall)          # router room, right wall
    d.rectangle([20, 180, 180, 186], fill=wall)          # router room, bottom wall, door 180-226
    d.rectangle([420, 20, 426, 180], fill=wall)
    d.rectangle([420, 260, 426, 420], fill=wall)
    d.rectangle([226, 180, 620, 186], fill=wall)
    path = folder / "plan.png"
    img.save(path)
    points = {str(i): {"xy": [x, y], "label": ""} for i, (x, y) in enumerate(
        [(90, 60), (160, 120), (60, 150), (300, 60), (380, 140), (500, 80), (580, 150), (100, 260), (250, 300),
         (350, 380), (480, 300), (560, 380), (200, 390), (60, 400), (520, 230), (320, 240)], 1)}
    plan = {"image": "plan.png", "m_per_px": 0.02, "router": [100, 100], "router_height_m": 0.1, "device_height_m": 0.45,
            "points": points, "holdout": ["3", "7", "11", "15"], "order": list(points), "doors": {"router room": [[180, 183], [220, 183]]}}
    (folder / "plan.json").write_text(json.dumps(plan))
    return folder / "plan.json"


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = cv.Plan.load(synthetic_plan(Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_walls_counted_once_each(self):
        self.assertEqual(cv.walls_crossed(self.plan.walls, (100, 100), (160, 120)), 0)
        self.assertEqual(cv.walls_crossed(self.plan.walls, (100, 100), (300, 60)), 1)
        self.assertEqual(cv.walls_crossed(self.plan.walls, (100, 100), (500, 80)), 2)
        self.assertEqual(cv.walls_crossed(self.plan.walls, (100, 100), (100, 300)), 1)

    def test_door_crossing(self):
        self.assertEqual(self.plan.geometry((300, 300))["doors"], ["router room"])
        self.assertEqual(self.plan.geometry((300, 60))["doors"], [])

    def test_door_path_goes_around_walls(self):
        routes = cv.DoorPaths(self.plan, self.plan.router)
        same_room = routes.route((160, 120))
        self.assertEqual(same_room["bends"], 0)
        below = routes.route((100, 300))            # below the router room's bottom wall: out through the door gap
        self.assertGreater(below["path_m"], self.plan.distance_m((100, 300)) + 0.5)
        self.assertGreaterEqual(below["bends"], 1)
        self.assertLess(below["snapped_m"], 0.1)
        closed = routes.route((300, 60))           # a room without a door: no open way, the nearest open place is used
        self.assertGreater(closed["snapped_m"], 0.5)

    def test_distance_includes_height(self):
        self.assertAlmostEqual(self.plan.distance_m((100, 100)), 0.35, places=2)
        self.assertAlmostEqual(self.plan.distance_m((200, 100)), math.hypot(2.0, 0.35), places=3)

    def test_fit_recovers_known_values(self):
        random.seed(3)
        truth = cv.Model(a=-38.0, n=3.0, wall_db=8.0)
        rows = []
        for pid, p in self.plan.points.items():
            g = self.plan.geometry(p["xy"])
            rows.append({"id": pid, "xy": p["xy"], **g, "rssi": float(truth.predict(g["distance_m"], g["walls"])) + random.gauss(0, 2)})
        result = cv.compare(self.plan, rows)
        m = result["_model"]
        self.assertAlmostEqual(m.n, 3.0, delta=0.6)
        self.assertAlmostEqual(m.wall_db, 8.0, delta=2.5)
        self.assertLess(result["multi-wall"]["holdout"]["rmse_db"], 4.0)
        self.assertGreater(result["free space (n = 2)"]["holdout"]["rmse_db"], result["multi-wall"]["holdout"]["rmse_db"])

    def test_map_and_render(self):
        m = cv.Model(a=-38.0, n=3.0, wall_db=8.0)
        values = cv.predict_map(self.plan, m, step=6)
        inside = values[~(values != values)]
        self.assertGreater(inside.max(), -45)
        self.assertLess(inside.min(), -60)
        out = cv.render(self.plan, values, Path(self.tmp.name) / "map.png", "test")
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
