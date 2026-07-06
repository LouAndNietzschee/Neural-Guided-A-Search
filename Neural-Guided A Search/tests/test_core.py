import math
import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from astar import (  # noqa: E402
    CLASSIC_HEURISTICS,
    astar_search,
    astar_search_dynamic,
    true_distance,
)
from environment import (  # noqa: E402
    Mission,
    STATIC_OBSTACLE,
    UAVEnvironment,
    build_environment,
)
from neural_heuristic import NeuralHeuristic  # noqa: E402


class ConstantModel:
    def predict_single(self, features):
        return float(features.sum())


class CoreBehaviorTests(unittest.TestCase):
    def test_reverse_ground_truth_matches_forward_dijkstra(self):
        env, _ = build_environment("simple", seed=42)
        start = (30, 25)
        goal = (25, 16)
        time = 3
        labels = true_distance(env, goal, time=time)
        mission = Mission(start=start, goal=goal, max_range=10_000)
        result = astar_search(
            env, mission, CLASSIC_HEURISTICS["zero"], time=time,
        )
        self.assertTrue(result.success)
        self.assertAlmostEqual(labels[start], result.cost, places=10)

    def test_dynamic_search_passes_arrival_time_to_heuristic(self):
        env, mission = build_environment("dynamic", seed=42)
        seen_times = []

        def timed_zero(node, goal, time=None):
            seen_times.append(time)
            return 0.0

        result = astar_search_dynamic(env, mission, timed_zero, max_nodes=500)
        self.assertLessEqual(result.nodes_expanded, 500)
        self.assertGreater(len(set(seen_times)), 1)
        self.assertEqual(min(seen_times), 0)

    def test_dynamic_path_is_safe_at_each_arrival_time(self):
        env, mission = build_environment("dynamic", seed=42)
        result = astar_search_dynamic(
            env, mission, CLASSIC_HEURISTICS["octile"],
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.path), len(result.time_path))
        self.assertTrue(all(
            env.is_passable(*position, time=time)
            for position, time in zip(result.path, result.time_path)
        ))

    def test_corner_cutting_is_blocked(self):
        env = UAVEnvironment(size=3)
        env.static_grid[0, 1] = STATIC_OBSTACLE
        env.static_grid[1, 0] = STATIC_OBSTACLE
        neighbors = dict(env.get_neighbors(0, 0, time=0))
        self.assertNotIn((1, 1), neighbors)

    def test_neural_cache_is_time_aware(self):
        env, _ = build_environment("dynamic", seed=42)
        heuristic = NeuralHeuristic(ConstantModel(), env)
        node = (20, 30)
        goal = (45, 45)
        heuristic(node, goal, time=0)
        heuristic(node, goal, time=1)
        self.assertEqual(len(heuristic.cache), 2)


if __name__ == "__main__":
    unittest.main()
