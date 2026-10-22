import unittest
import numpy as np
from scipy.optimize import linprog
from src.subsidy_support import subsidy_rows


class SubsidyBoundaryTests(unittest.TestCase):
    def test_minimum_and_maximum_excess_match_policy_for_every_count(self):
        rows = subsidy_rows(0, 1, 2, 20)
        matrix, rhs = [], []
        for indices, coefficients, sense, limit in rows:
            row = np.zeros(3)
            row[indices] = coefficients
            matrix.append(row if sense == 'L' else -row)
            rhs.append(limit if sense == 'L' else -limit)
        for count in range(21):
            for trigger in (0, 1):
                feasible = trigger == int(count >= 10)
                for sign in (-1, 1):
                    with self.subTest(count=count, trigger=trigger, sign=sign):
                        solution = linprog([0, 0, sign], A_ub=matrix, b_ub=rhs,
                                           bounds=[(count, count), (trigger, trigger), (0, None)], method='highs')
                        self.assertEqual(solution.success, feasible)
                        if feasible:
                            self.assertAlmostEqual(solution.x[2], max(count-10, 0))

    def test_invalid_bounds_are_rejected(self):
        for maximum, threshold in ((9, 10), (20, 0), (20.5, 10)):
            with self.assertRaises(ValueError):
                subsidy_rows(0, 1, 2, maximum, threshold)
