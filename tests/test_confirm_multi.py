import unittest

from src.analysis.confirm_multi import continue_all_value, solve_exact, wait_each_value

DIST = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}


class TwoStockoutTests(unittest.TestCase):
    def test_exact_policy_never_below_the_two_rules(self):
        for deadline in (8, 9, 10):
            for window in (deadline, deadline - 2):
                for reject in (0.0, 0.2):
                    full = solve_exact(DIST, reject, window, deadline)
                    baseline = max(wait_each_value(DIST, reject, window, deadline),
                                   continue_all_value(DIST, reject, window, deadline))
                    self.assertGreaterEqual(full + 1e-9, baseline)

    def test_all_rejected_leaves_only_the_other_item(self):
        full = solve_exact(DIST, 1.0, 10, 10)
        self.assertAlmostEqual(full, 1.0)

    def test_invalid_window_rejected(self):
        with self.assertRaises(ValueError):
            # A negative window has no meaning; the exact solver should refuse it.
            solve_exact(DIST, 0.0, -1, 8)


if __name__ == "__main__":
    unittest.main()
