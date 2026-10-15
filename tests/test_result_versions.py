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
