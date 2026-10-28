import unittest

from src.analysis.mlor_dp2 import best_routes, route_cost, solve
from src.analysis.mlor_scale import PENALTY, make_instance


class MlorDpTests(unittest.TestCase):
    def test_age_aware_beats_blind_on_the_first_instance(self):
        stores = make_instance(0)
        aware, _ = solve(best_routes(stores, "actual", True))
        blind_planned, chosen = solve(best_routes(stores, "zero", False))
        infeasible = 0
        for warehouse_index, subset in chosen:
            order = next(order for sub, _, order in best_routes(stores, "zero", False)[warehouse_index]
                         if sub == subset)
            _, count = route_cost(warehouse_index, order, stores, "actual")
            infeasible += count
        blind_actual = blind_planned + PENALTY * infeasible
        self.assertGreater(infeasible, 0)
        self.assertLess(aware, blind_actual)

    def test_aware_solution_is_feasible(self):
        stores = make_instance(0)
        routes = best_routes(stores, "actual", True)
        for warehouse_index in routes:
            for subset, cost, order in routes[warehouse_index]:
                _, infeasible = route_cost(warehouse_index, order, stores, "actual")
                self.assertEqual(infeasible, 0)


if __name__ == "__main__":
    unittest.main()
