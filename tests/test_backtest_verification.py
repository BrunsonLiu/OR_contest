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
                                  str(self.folder), "--report", str(self.folder/"must-not-exist.json")], capture_output=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse((self.folder/"must-not-exist.json").exists())
