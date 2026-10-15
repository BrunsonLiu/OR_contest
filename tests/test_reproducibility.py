"""Regression tests for real forecasting and input-contract failure modes."""
import json
import ast
import os
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest
from unittest.mock import Mock

import numpy as np
import pandas as pd

from src.forecasting import evaluate_and_save, time_features
from src.runtime import ROOT, read_forecast, solver_evidence


class ForecastContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = pd.read_csv(ROOT / "results/question3/订单需求量预测结果文件_sota.csv")

    def validate(self, frame):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecast.csv"
            frame.to_csv(path, index=False)
            return read_forecast(path)

    def test_saved_forecast_satisfies_contract(self):
        self.assertEqual(self.validate(self.reference).shape, (204, 9))

    def test_duplicate_and_missing_customer_sku_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(pd.concat([self.reference, self.reference.iloc[:1]], ignore_index=True))
        with self.assertRaises(ValueError):
            self.validate(self.reference.iloc[1:])

    def test_nonfinite_and_negative_demand_rejected(self):
        for value in (float("nan"), float("inf"), -1):
            with self.subTest(value=value):
                frame = self.reference.copy()
                frame.iloc[0, 2] = value
                with self.assertRaises(ValueError):
                    self.validate(frame)

    def test_wrong_forecast_week_rejected(self):
        frame = self.reference.rename(columns={self.reference.columns[2]: "2016/06/23"})
        with self.assertRaises(ValueError):
            self.validate(frame)


class TemporalValidationTests(unittest.TestCase):
    def test_future_index_continues_training_index(self):
        training = time_features(pd.date_range("2016-06-01", periods=23))
        future = time_features(pd.date_range("2016-06-24", periods=7))
        self.assertEqual(training["time_idx"].iloc[-1] + 1, future["time_idx"].iloc[0])

    def test_holdout_is_not_exposed_to_training_or_scored_against_future(self):
        dates = pd.date_range("2016-06-01", periods=23)
        values = np.arange(23, dtype=float).reshape(1, -1)
        frame = pd.DataFrame({"Name": ["example"], "SKU": ["dm"]})
        for index, date in enumerate(dates):
            frame[str(date.date())] = values[:, index]
        calls = []

        def predict(keys, training, history_dates, target_dates):
            self.assertEqual(list(keys.columns), ["Name", "SKU"])
            self.assertLess(history_dates[-1], target_dates[0])
            calls.append(training.shape[1])
            if training.shape[1] == 16:
                np.testing.assert_array_equal(training, values[:, :16])
                return np.arange(16, 23, dtype=float).reshape(1, -1)
            return np.full((1, 7), 1000.0)

        with tempfile.TemporaryDirectory() as folder:
            report = evaluate_and_save("test", "future.csv", predict, frame, dates, values, Path(folder))
            self.assertEqual(report["validation"]["rmse"], 0)
            self.assertEqual(calls, [16, 23])
            future = pd.read_csv(Path(folder) / "future.csv")
            self.assertEqual(future.iloc[0, 2], 1000)
            json.loads((Path(folder) / "metrics_test.json").read_text(encoding="utf-8"))

    def test_no_incumbent_does_not_read_objective(self):
        problem = Mock()
        problem.solution.is_primal_feasible.return_value = False
        problem.solution.get_status.return_value = 108
        problem.solution.get_status_string.return_value = "time limit exceeded, no integer solution"
        problem.get_problem_type.return_value = "LP"
        result = solver_evidence(problem)
        self.assertFalse(result["has_incumbent"])
        self.assertNotIn("objective", result)
        problem.solution.get_objective_value.assert_not_called()

    def test_robust_no_incumbent_preserves_status_without_extracting_solution(self):
        source = ROOT / "src/solvers/question4/solve_problem4_robust.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "solve_and_extract")
        namespace = {"_configure_solver": lambda problem: None, "_record_solver": lambda problem: {}}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        problem = Mock()
        problem.solution.get_status.return_value = 108
        problem.solution.get_status_string.return_value = "time limit exceeded, no integer solution"
        problem.solution.is_primal_feasible.return_value = False
        result = namespace["solve_and_extract"](problem, {}, 0.04)
        self.assertIsNone(result["total_cost"])
        self.assertEqual(result["status_code"], 108)
        problem.solution.get_objective_value.assert_not_called()
        problem.solution.get_values.assert_not_called()


class LauncherTests(unittest.TestCase):
    def test_external_launch_isolated_output_and_duplicate_run_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            (root / "src").mkdir(parents=True)
            shutil.copyfile(ROOT / "run.py", root / "run.py")
            (root / "src/probe.py").write_text(
                "import os\nfrom pathlib import Path\n"
                "output = Path(os.environ['OR_RESULTS_ROOT'])\n"
                "assert Path.cwd() == Path(__file__).resolve().parents[1]\n"
                "(output / 'probe.txt').write_text('isolated', encoding='utf-8')\n",
                encoding="utf-8")
            command = [sys.executable, str(root / "run.py"), "--script", "src/probe.py", "--experiment", "test"]
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            first = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertTrue((root / "results/experiments/test/probe.txt").is_file())
            self.assertFalse((root / "results/probe.txt").exists())
            manifest = json.loads((root / "results/experiments/test/_runs/probe/run.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            repeated = subprocess.run(command, cwd=folder, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertNotEqual(repeated.returncode, 0)

    def test_archived_script_cannot_silently_bypass_output_isolation(self):
        result = subprocess.run([sys.executable, str(ROOT / "run.py"), "--script",
                                 "archive/diagnostics/checks/check_missing.py", "--experiment", "blocked-archive"],
                                cwd=ROOT, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((ROOT / "results/experiments/blocked-archive").exists())


if __name__ == "__main__":
    unittest.main()
