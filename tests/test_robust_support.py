"""Compare exact budget dual rows against exhaustive small-set vertices."""
import ast
import itertools
from pathlib import Path
import unittest

import numpy as np
from scipy.optimize import linprog
from src.robust_support import budget_support, service_ratio_rows


def vertices(n, budget):
    result = []
    for point in itertools.product((0.0, 1.0), repeat=n):
        if sum(point) <= budget:
            result.append(np.array(point))
        remainder = budget - sum(point)
        if 0 < remainder < 1:
            for i, value in enumerate(point):
                if value == 0:
                    fractional = list(point)
                    fractional[i] = remainder
                    result.append(np.array(fractional))
    return result


class RobustBudgetTests(unittest.TestCase):
    def test_support_matches_all_vertices_including_negative_coefficients(self):
        for coefficients in ((3, -5, 2), (-1, -2, -3), (1, 9, 4)):
            for budget in (0, 0.4, 1, 1.7, 3, 4):
                with self.subTest(coefficients=coefficients, budget=budget):
                    exact = max(float(np.dot(coefficients, point)) for point in vertices(3, budget))
                    self.assertAlmostEqual(budget_support(coefficients, budget), exact)

    def test_service_dual_feasibility_matches_every_demand_vertex(self):
        nominal = np.array([40.0, 55.0, 5.0])
        deltas = np.array([8.0, 20.0, 10.0])
        ratio, n = 0.95, 3
        for assignment in itertools.product((0, 1), repeat=n):
            for budget in (0, 0.5, 1, 1.7, 3):
                with self.subTest(assignment=assignment, budget=budget):
                    rows = service_ratio_rows(nominal, deltas, range(n), ratio, budget, n, range(n+1, 2*n+1))
                    matrix, rhs = [], []
                    for indices, coefficients, sense, bound in rows:
                        row = np.zeros(2*n+1)
                        row[indices] = coefficients
                        sign = -1 if sense == "G" else 1
                        matrix.append(sign*row)
                        rhs.append(sign*bound)
                    solution = linprog(np.zeros(2*n+1), A_ub=matrix, b_ub=rhs,
                                       bounds=[(v, v) for v in assignment] + [(0, None)]*(n+1), method="highs")
                    worst_deficit = max(float(np.dot(ratio-np.array(assignment), nominal+deltas*z))
                                        for z in vertices(n, budget))
                    self.assertEqual(solution.success, worst_deficit <= 1e-8)

    def test_all_on_time_is_feasible_when_old_denominator_test_fails(self):
        nominal, delta, ratio, budget = [50, 50], [20, 20], 0.95, 1
        old_required = ratio*(sum(nominal)+budget_support(delta, budget))
        self.assertGreater(old_required, sum(nominal))
        deficit = sum((ratio-1)*d for d in nominal) + budget_support([(ratio-1)*d for d in delta], budget)
        self.assertLessEqual(deficit, 0)

    def test_filtered_cdc_uses_full_daily_budget(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "src/solvers/question4/solve_problem4_robust.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "compute_worst_case_total_demand")
        keys = [("a", "dm"), ("a", "im"), ("b", "dm"), ("b", "im")]
        env = {"budget_support": budget_support, "all_demand_keys_period": {0: keys},
               "demand_nominal": {0: dict.fromkeys(keys, 10)}, "demand_delta": {0: dict.fromkeys(keys, 5)}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "CDC test", "exec"), env)
        self.assertAlmostEqual(env["compute_worst_case_total_demand"](0, 0.25, "dm"), 25)


if __name__ == "__main__":
    unittest.main()
