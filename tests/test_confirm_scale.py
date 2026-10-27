import unittest

from src.analysis.confirm_policy_compare import solve_stochastic
from src.analysis.confirm_scale import positions_for, solve_exact, solve_rules


class ConfirmationScaleTests(unittest.TestCase):
    def test_one_item_matches_the_four_node_stochastic_dp(self):
        for dist in ({2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}, {1: 1.0}):
            for reject in (0.0, 0.2):
                for deadline in (6, 8):
                    for window in (deadline, deadline - 2):
                        old = solve_stochastic(3, dist, reject, window, deadline)
                        new = solve_exact(positions_for(1), dist, reject, window, deadline,
                                          [0.0, 0.0, 1.0, 1.0])
                        self.assertAlmostEqual(old, new)

    def test_exact_policy_never_below_the_two_rules(self):
        for n_items in (1, 2, 3):
            nodes = positions_for(n_items)
            values = [0.0, 0.0, 2.0] + [1.0] * n_items
            for reject in (0.0, 0.2):
                for deadline in (nodes[-1] - 1, nodes[-1] + 1):
                    full = solve_exact(nodes, {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}, reject,
                                       deadline, deadline, values)
                    suspend, keep = solve_rules(nodes, values, {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2},
                                                reject, deadline, deadline)
                    self.assertGreaterEqual(full + 1e-9, max(suspend, keep))

    def test_invalid_instance_rejected(self):
        with self.assertRaises(ValueError):
            positions_for(0)
        with self.assertRaises(ValueError):
            solve_exact([0.0, 1.0], {1: 1.0}, 0.0, 2, 2, [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
