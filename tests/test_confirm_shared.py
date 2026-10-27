import unittest

from src.analysis.confirm_shared import family_values, solve_exact

DIST = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}


class SharedSubstituteTests(unittest.TestCase):
    def test_exact_policy_never_below_the_rule_family(self):
        for deadline in (6, 8, 10):
            for window in (deadline, deadline - 2):
                for reject in (0.0, 0.2):
                    full = solve_exact(DIST, reject, window, deadline)
                    best = max(family_values(DIST, reject, window, deadline).values())
                    self.assertGreaterEqual(full + 1e-9, best)

    def test_all_rejected_gives_zero(self):
        self.assertAlmostEqual(solve_exact(DIST, 1.0, 10, 10), 0.0)


if __name__ == "__main__":
    unittest.main()
