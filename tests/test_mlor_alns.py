import unittest

from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import make_instance


class MlorAlnsTests(unittest.TestCase):
    def test_alns_improves_the_greedy_initial_solution(self):
        stores = make_instance(0)
        _, routes, _ = construct(stores, "actual", True)
        served = {store for route_list in routes.values() for order in route_list for store in order}
        unserved = [store for store in range(len(stores)) if store not in served]
        initial = solution_cost(routes, unserved, stores)
        best, _ = alns(stores, iterations=100, seed=0)
        self.assertLess(best, initial - 1e-6)

    def test_alns_is_deterministic_for_a_seed(self):
        stores = make_instance(0)
        first, _ = alns(stores, iterations=50, seed=0)
        second, _ = alns(stores, iterations=50, seed=0)
        self.assertAlmostEqual(first, second, places=6)


if __name__ == "__main__":
    unittest.main()
