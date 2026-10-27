import unittest

from src.analysis.confirm_grid2d import solve_exact
from src.analysis.confirm_grid_rules import family_values, policy_value

DIST = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}


class GridRuleFamilyTests(unittest.TestCase):
    def test_exact_never_below_the_enriched_family(self):
        for deadline in (6, 8, 10):
            for window in (deadline, deadline - 2):
                for reject in (0.0, 0.2):
                    full = solve_exact(DIST, reject, window, deadline)
                    best = max(family_values(DIST, reject, window, deadline).values())
                    self.assertGreaterEqual(full + 1e-9, best)

    def test_stop_before_substitute_matches_the_eight_minute_case(self):
        # Serving two other items before the substitute is the rule that closes
        # the previously observed 0.8 gap at D=8.
        value = policy_value(DIST, 0.2, 8, 8, True, 0, "nearest", False, 2)
        self.assertAlmostEqual(value, 3.8)


if __name__ == "__main__":
    unittest.main()
