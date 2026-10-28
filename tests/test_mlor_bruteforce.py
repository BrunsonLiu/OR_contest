import unittest
from itertools import permutations, product

from src.analysis.mlor_mechanism import ORIGINAL_AGES, best_routes, route_cost, solve
from src.analysis.mlor_scale import OPEN_COST, WAREHOUSES, make_instance


def set_partitions(items):
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for partition in set_partitions(rest):
        for index in range(len(partition)):
            yield partition[:index] + [[first] + partition[index]] + partition[index + 1:]
        yield [[first]] + partition


class MlorBruteForceTests(unittest.TestCase):
    def test_subset_dp_matches_brute_force_on_four_stores(self):
        stores = make_instance(0, 4)
        n_stores = len(stores)
        n_warehouses = len(WAREHOUSES)

        routes = best_routes(stores, ORIGINAL_AGES, True, True)
        dp_cost, _ = solve(routes, n_stores)

        best = float("inf")
        for partition in set_partitions(list(range(n_stores))):
            for assignment in product(range(n_warehouses), repeat=len(partition)):
                opened = set(assignment)
                total = OPEN_COST * len(opened)
                feasible = True
                for block, warehouse_index in zip(partition, assignment):
                    best_route = None
                    for order in permutations(block):
                        cost, infeasible = route_cost(warehouse_index, order, stores,
                                                      ORIGINAL_AGES, True, True)
                        if infeasible == 0 and (best_route is None or cost < best_route):
                            best_route = cost
                    if best_route is None:
                        feasible = False
                        break
                    total += best_route
                if feasible:
                    best = min(best, total)
        self.assertAlmostEqual(dp_cost, best, places=6)


if __name__ == "__main__":
    unittest.main()
