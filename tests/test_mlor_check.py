import unittest

from src.analysis.mlor_check2 import best, evaluate_plan


class MlorCheckTests(unittest.TestCase):
    def test_age_aware_is_feasible(self):
        aware = best("actual", True)
        self.assertAlmostEqual(aware[0], 260.0, places=6)
        self.assertEqual(aware[1], 0)

    def test_age_blind_is_cheaper_on_paper_but_infeasible(self):
        blind = best("zero", False)
        self.assertAlmostEqual(blind[0], 220.0, places=6)
        actual_cost, infeasible = evaluate_plan(blind[2], "actual")
        self.assertAlmostEqual(actual_cost, 420.0, places=6)
        self.assertEqual(infeasible, 1)

    def test_age_aware_beats_the_age_blind_execution(self):
        aware = best("actual", True)
        blind = best("zero", False)
        actual_cost, _ = evaluate_plan(blind[2], "actual")
        self.assertLess(aware[0], actual_cost)


if __name__ == "__main__":
    unittest.main()
