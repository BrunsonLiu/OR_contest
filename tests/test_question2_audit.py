from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

import pandas as pd
from src.runtime import ROOT
from tools.audit_results import audit


class Question2AuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        baseline = ROOT/"results/experiments/final-q2-loss-20261015"
        shutil.copytree(baseline/"question2", self.root/"question2")
        evidence = self.root/"_runs/q2-loss"
        evidence.mkdir(parents=True)
        shutil.copyfile(baseline/"_runs/q2-loss/solver_metrics.jsonl", evidence/"solver_metrics.jsonl")

    def test_real_policy_and_all_cost_components_reconcile(self):
        rows = audit(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["issues"], [])
        self.assertTrue(rows[0]["smart_policy_checked"])
        self.assertGreater(rows[0]["loss_detail_rows_checked"], 204)

    def test_counting_loss_twice_is_rejected(self):
        path = self.root/"question2/仓网业务表现文件_运输损耗_cplex.csv"
        frame = pd.read_csv(path)
        frame.iloc[0, 2] += frame.iloc[0, 8]
        frame.to_csv(path, index=False)
        self.assertTrue(audit(self.root)[0]["issues"])

    def test_false_smart_decision_is_rejected(self):
        path = self.root/"question2/仓库决策文件_运输损耗_cplex.csv"
        frame = pd.read_csv(path)
        frame.loc[frame.smart.eq(1).idxmax(), "smart"] = 0
        frame.to_csv(path, index=False)
        self.assertTrue(audit(self.root)[0]["issues"])

    def test_wrong_loss_detail_is_rejected(self):
        path = self.root/"question2/仓→店损耗明细文件_完整版_cplex.csv"
        frame = pd.read_csv(path)
        frame.loc[0, "单吨损耗成本(万元)"] += 1
        frame.to_csv(path, index=False)
        self.assertTrue(audit(self.root)[0]["issues"])

    def test_empty_directory_cannot_pass_cli_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder)/"checks.json"
            process = subprocess.run([sys.executable, str(ROOT/"tools/audit_results.py"), folder, "--report", str(report)], capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(report.exists())

    def test_nonfinite_cost_cannot_evade_residual_checks(self):
        path = self.root/"question2/仓网业务表现文件_运输损耗_cplex.csv"
        frame = pd.read_csv(path)
        frame.iloc[0, 2] = float("nan")
        frame.to_csv(path, index=False)
        with self.assertRaises(ValueError):
            audit(self.root)

    def test_missing_policy_is_incomplete_not_success(self):
        (self.root/"question2/仓库决策文件_运输损耗_cplex.csv").unlink()
        report = self.root/"validation/checks.json"
        process = subprocess.run([sys.executable, str(ROOT/"tools/audit_results.py"), str(self.root),
                                  "--report", str(report)], capture_output=True)
        self.assertEqual(process.returncode, 2)
        self.assertTrue(report.exists())

    def test_missing_solver_evidence_is_incomplete_not_success(self):
        # Without solver_metrics.jsonl the exported total cannot be tied to a
        # real solve; this is an evidence gap (exit 2), never a silent pass.
        (self.root/"_runs/q2-loss/solver_metrics.jsonl").unlink()
        report = self.root/"validation/checks.json"
        process = subprocess.run([sys.executable, str(ROOT/"tools/audit_results.py"), str(self.root),
                                  "--report", str(report)], capture_output=True)
        self.assertEqual(process.returncode, 2)
        rows = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(any(r.get("limitations") for r in rows))

    def test_missing_q4_daily_file_is_incomplete_not_success(self):
        # A partial daily export used to be skipped day by day and still exit 0.
        source = ROOT/"results/experiments/audit-fixed-20261015/question4/problem4_loss_v2"
        shutil.copytree(source, self.root/"question4/problem4_loss_v2")
        evidence = self.root/"_runs/q4-loss"
        evidence.mkdir(parents=True)
        shutil.copyfile(ROOT/"results/experiments/audit-fixed-20261015/_runs/q4-loss/run.json",
                        evidence/"run.json")
        (self.root/"question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-27.csv").unlink()
        report = self.root/"validation/checks.json"
        process = subprocess.run([sys.executable, str(ROOT/"tools/audit_results.py"), str(self.root),
                                  "--report", str(report)], capture_output=True)
        self.assertEqual(process.returncode, 2)
        rows = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(any("2016-06-27" in m for r in rows for m in r.get("limitations", [])))
