import unittest

from src.analysis.confirm_policy_compare import continue_value, solve_stochastic, suspend_value


class ConfirmationPolicyTests(unittest.TestCase):
    def test_point_mass_reproduces_deterministic_cases(self):
        fast = solve_stochastic(10, {1: 1.0}, 0.0, 12, 12)
        slow = solve_stochastic(10, {5: 1.0}, 0.0, 12, 12)
        self.assertAlmostEqual(fast, 2.0)
        self.assertAlmostEqual(slow, 1.0)

    def test_always_rejected_keeps_only_the_other_item(self):
        self.assertAlmostEqual(solve_stochastic(10, {1: 1.0}, 1.0, 12, 12), 1.0)
        self.assertAlmostEqual(suspend_value(10, {1: 1.0}, 1.0, 12, 12), 1.0)
        self.assertAlmostEqual(continue_value(10, {1: 1.0}, 1.0, 12, 12), 1.0)

    def test_window_counts_reply_at_request_plus_delay(self):
        # Request at minute 1: a delay-6 reply arrives at minute 7 and is too late for C=6.
        late = solve_stochastic(12, {6: 1.0}, 0.0, 6, 10)
        self.assertAlmostEqual(late, 0.0)

    def test_full_policy_never_below_the_two_rules(self):
        for other_position in (8.0, 10.0, 12.0):
            for dist in ({1: 0.5, 2: 0.3, 3: 0.2}, {3: 0.3, 4: 0.3, 5: 0.2, 6: 0.2}):
                for reject in (0.0, 0.2):
                    for deadline in (10, 12, 14):
                        for window in (deadline, max(deadline - 4, 1)):
                            full = solve_stochastic(other_position, dist, reject, window, deadline)
                            baseline = max(suspend_value(other_position, dist, reject, window, deadline),
                                           continue_value(other_position, dist, reject, window, deadline))
                            self.assertGreaterEqual(full + 1e-9, baseline)

    def test_invalid_distribution_rejected(self):
        with self.assertRaises(ValueError):
            solve_stochastic(10, {1: 0.5}, 0.0, 12, 12)
        with self.assertRaises(ValueError):
            solve_stochastic(10, {1: 1.0}, 1.5, 12, 12)


if __name__ == "__main__":
    unittest.main()
