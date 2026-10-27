import unittest

from src.analysis.confirm_instance_check import realised_frozen_plan, solve_instance


class ConfirmationInstanceTests(unittest.TestCase):
    def test_reply_delay_changes_feasible_delivery(self):
        fast = solve_instance(10, 1, 12, 12)
        slow = solve_instance(10, 5, 12, 12)
        self.assertEqual((fast["value"], fast["finish"]), (2.0, 10.0))
        self.assertEqual(slow["value"], 1.0)

    def test_preapproved_substitute_is_optimistic_under_full_rules(self):
        slow = solve_instance(10, 5, 12, 12, preapproved=True)
        self.assertEqual(slow["value"], 2.0)
        realised = realised_frozen_plan(slow["plan"], 10, 5, 12, 12)
        self.assertTrue(realised["violation"])
        self.assertEqual(realised["value"], 1.0)

    def test_fast_reply_does_not_violate(self):
        fast = solve_instance(10, 1, 12, 12, preapproved=True)
        realised = realised_frozen_plan(fast["plan"], 10, 1, 12, 12)
        self.assertFalse(realised["violation"])
        self.assertEqual(realised["value"], 2.0)

    def test_closing_window_can_remove_the_substitute(self):
        no_window = solve_instance(10, 1, 12, 12)
        closed = solve_instance(10, 1, 1, 12)
        self.assertEqual(no_window["value"], 2.0)
        self.assertEqual(closed["value"], 1.0)

    def test_invalid_instance_rejected(self):
        with self.assertRaises(ValueError):
            solve_instance(2, 1, 12, 12)
        with self.assertRaises(ValueError):
            solve_instance(10, -1, 12, 12)


if __name__ == "__main__":
    unittest.main()
