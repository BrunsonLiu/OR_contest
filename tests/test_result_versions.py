import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.runtime import ROOT, loss_results_dir


class ResultVersionTests(unittest.TestCase):
    def test_version_paths_stay_in_selected_experiment(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"OR_RESULTS_ROOT": folder}, clear=True):
                self.assertEqual(loss_results_dir(), Path(folder).resolve()/"question4/problem4_loss_v2/output_result")
                os.environ["OR_LOSS_VERSION"] = "legacy"
                self.assertEqual(loss_results_dir(), Path(folder).resolve()/"question4/problem4_loss/output_result")
                os.environ["OR_LOSS_VERSION"] = "../outside"
                with self.assertRaises(ValueError):
                    loss_results_dir()

    def test_solver_cannot_write_selected_historical_version(self):
        result = subprocess.run([sys.executable, str(ROOT/"run.py"), "q4-loss", "--loss-version", "legacy"],
                                capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"--loss-version", result.stderr)

    def test_question4_summary_open_count_is_computed_not_literal(self):
        # A hardcoded 19 once disagreed with the daily files (18 on 2016-06-24).
        for name in ("solve_problem4_no_loss.py", "solve_problem4_loss.py"):
            source = ROOT / "src/solvers/question4" / name
            tree = ast.parse(source.read_text(encoding="utf-8"))
            summary = None
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "DataFrame" and node.args
                        and isinstance(node.args[0], ast.List)):
                    continue
                dictionary = next((element for element in node.args[0].elts if isinstance(element, ast.Dict)), None)
                if dictionary and any(isinstance(key, ast.Constant) and key.value == "指标" for key in dictionary.keys):
                    summary = dictionary
            self.assertIsNotNone(summary, f"{name} 未找到汇总行")
            value = next(value for key, value in zip(summary.keys, summary.values)
                         if isinstance(key, ast.Constant) and key.value == "开仓数量")
            self.assertIsInstance(value, ast.Name, f"{name} 汇总开仓数量必须是计算值而非字面量")
            self.assertEqual(value.id, "final_open_wh_count", f"{name} 汇总开仓数量来源不符")
