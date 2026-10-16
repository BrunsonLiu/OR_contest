"""Reject incomplete or mislabelled saved reports, using a preserved real baseline."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from src.runtime import ROOT
from tools.verify_backtest_results import verify


class BacktestVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)/"backtests"
        shutil.copytree(ROOT/"results/experiments/rolling-20261015/question3/backtests", self.folder)
        self.path = self.folder/"rolling_backtest.json"
        self.report = json.loads(self.path.read_text(encoding="utf-8"))
        self.methods = set(self.report["summary"])

    def save(self):
        self.path.write_text(json.dumps(self.report), encoding="utf-8")

    def test_complete_real_predictions_are_verified(self):
        result = verify(self.folder, self.methods)
        self.assertEqual(result["prediction_files_checked"], 36)
        self.assertEqual(len(result["inputs_sha256"]), 37)
        self.assertTrue(result["method_set_asserted"])
        self.assertTrue(result["weekly_baseline_verified"])

    def test_omitted_expected_methods_is_flagged_not_asserted(self):
        # Self-referential check: without an explicit target the method set is
        # only compared to itself, so completeness was not actually asserted.
        result = verify(self.folder)
        self.assertFalse(result["method_set_asserted"])

    def test_report_does_not_claim_a_baseline_that_never_ran(self):
        # The baseline recompute is gated on a SeasonalNaive row; the report must
        # not assert it ran when none exists (baseline dropped from the run).
        import math
        self.report["summary"].pop("SeasonalNaive")
        self.report["windows"] = [row for row in self.report["windows"] if row["method"] != "SeasonalNaive"]
        for window in {row["window"] for row in self.report["windows"]}:
            peers = [row for row in self.report["windows"] if row["window"] == window]
            for row in peers:
                row["rank"] = 1+sum(other["metrics"]["rmse"] < row["metrics"]["rmse"]-1e-12 for other in peers)
        for method, summary in self.report["summary"].items():
            rows = [row for row in self.report["windows"] if row["method"] == method]
            points = sum(row["points"] for row in rows)
            summary.update(best_rank=min(row["rank"] for row in rows),
                           worst_rank=max(row["rank"] for row in rows),
                           windows_tied_for_best=sum(row["rank"] == 1 for row in rows),
                           forecast_events=points,
                           mean_window_rmse=sum(row["metrics"]["rmse"] for row in rows)/len(rows),
                           forecast_event_rmse=math.sqrt(
                               sum(row["points"]*row["metrics"]["rmse"]**2 for row in rows)/points))
        self.save()
        result = verify(self.folder, self.methods - {"SeasonalNaive"})
        self.assertFalse(result["weekly_baseline_verified"])
        self.assertNotIn("weekly SeasonalNaive baseline", result["checks"])

    def test_cli_requires_expected_methods(self):
        report = self.folder/"must-not-exist.json"
        process = subprocess.run([sys.executable, str(ROOT/"tools/verify_backtest_results.py"),
                                  str(self.folder), "--report", str(report)], capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(report.exists())

    def test_silently_dropped_method_is_rejected(self):
        self.report["summary"].pop("LightGBM")
        self.report["windows"] = [row for row in self.report["windows"] if row["method"] != "LightGBM"]
        self.save()
        with self.assertRaises(AssertionError):
            verify(self.folder, self.methods)

    def test_missing_or_duplicate_window_rows_are_rejected(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                self.report = json.loads((ROOT/"results/experiments/rolling-20261015/question3/backtests/rolling_backtest.json").read_text(encoding="utf-8"))
                if duplicate:
                    self.report["windows"].append(self.report["windows"][0].copy())
                else:
                    self.report["windows"].pop()
                self.save()
                with self.assertRaises(AssertionError):
                    verify(self.folder)

    def test_false_training_dates_and_rank_are_rejected(self):
        for key, value in (("train_end", "2016-06-01"), ("rank", 999)):
            with self.subTest(key=key):
                original = self.report["windows"][0][key]
                self.report["windows"][0][key] = value
                self.save()
                with self.assertRaises(AssertionError):
                    verify(self.folder)
                self.report["windows"][0][key] = original

    def test_optimized_python_cannot_disable_acceptance_checks(self):
        process = subprocess.run([sys.executable, "-O", str(ROOT/"tools/verify_backtest_results.py"),
                                  str(self.folder), "--expected-methods", ",".join(sorted(self.methods)),
                                  "--report", str(self.folder/"must-not-exist.json")], capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse((self.folder/"must-not-exist.json").exists())
