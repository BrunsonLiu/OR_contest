"""Regression tests for the fingerprint check's silent-pass guards."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime import ROOT
import tools.check_line_endings as cle
import tools.check_repository as cr


class RepositoryTaskTableTests(unittest.TestCase):
    def test_empty_task_table_fails(self):
        # An empty TASKS dict makes the entry-existence check assert nothing.
        source = (ROOT/"run.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("src/solvers", "src/analysis", "src/visualization", "data/raw",
                         "results/question1", "results/question2", "results/question3",
                         "results/question4", "docs", "archive/diagnostics", "requirements"):
                (root/name).mkdir(parents=True, exist_ok=True)
            (root/"run.py").write_text(source.replace("TASKS = {", "TASKS = {}\n_DISABLED = {", 1),
                                       encoding="utf-8")
            import io
            import contextlib
            buffer = io.StringIO()
            with patch.object(cr, "ROOT", root), patch.object(cr, "INCOMPLETE", root/"nonexistent"):
                with contextlib.redirect_stdout(buffer):
                    cr.check()
            self.assertIn("TASKS 为空", buffer.getvalue())


class LossVersionFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT/"docs/audits/2026-10-15", self.root/"docs/audits/2026-10-15")
        # A real version folder the record points at, so only the file list varies.
        (self.root/"results/question4/problem4_loss/output_result").mkdir(parents=True)
        shutil.copyfile(ROOT/"data/raw/df_proc.csv",
                        self.root/"results/question4/problem4_loss/output_result/sample.csv")

    def run_check(self):
        errors = []
        with patch.object(cle, "ROOT", self.root):
            cle.check_loss_version_fingerprints(errors)
        return errors

    def record_path(self):
        return self.root/"docs/audits/2026-10-15/loss_versions.json"

    def test_missing_record_fails(self):
        self.record_path().unlink()
        self.assertTrue(self.run_check())

    def test_empty_top_level_versions_fails(self):
        self.record_path().write_text(json.dumps({"versions": {}}), encoding="utf-8")
        self.assertTrue(self.run_check())

    def test_per_version_missing_file_list_fails(self):
        # An entry present but with no files used to assert nothing silently.
        record = {"versions": {"legacy": {"folder": "results/question4/problem4_loss/output_result"}}}
        self.record_path().write_text(json.dumps(record), encoding="utf-8")
        errors = self.run_check()
        self.assertTrue(any("缺少文件清单" in message for message in errors))

    def test_experiments_versions_are_out_of_scope(self):
        record = {"versions": {"corrected_v2": {
            "folder": "results/experiments/x/question4/problem4_loss_v2/output_result", "files": {}}}}
        self.record_path().write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.run_check(), [])

if __name__ == "__main__":
    unittest.main()
