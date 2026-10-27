import unittest

from src.analysis.confirm_grid2d import (THRESHOLDS, _skip_A_value, _visit_A_then_others,
                                        solve_exact, threshold_value, wait_value)

DIST = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}


class GridConfirmationTests(unittest.TestCase):
    def test_exact_policy_never_below_the_rules_with_skip_option(self):
        for deadline in (6, 8, 10):
            for window in (deadline, deadline - 2):
                for reject in (0.0, 0.2):
                    full = solve_exact(DIST, reject, window, deadline)
                    best_rule = max(
                        wait_value(DIST, reject, window, deadline),
                        _visit_A_then_others(DIST, reject, window, deadline),
                        max(threshold_value(DIST, reject, window, deadline, threshold)
                            for threshold in THRESHOLDS))
                    self.assertGreaterEqual(full + 1e-9, best_rule)

    def test_all_rejected_equals_skipping_the_stockout(self):
        full = solve_exact(DIST, 1.0, 10, 10)
        self.assertAlmostEqual(full, _skip_A_value(DIST, 1.0, 10, 10))

    def test_invalid_instance_rejected(self):
        with self.assertRaises(ValueError):
            solve_exact(DIST, 0.0, 10, -1)


if __name__ == "__main__":
    unittest.main()
