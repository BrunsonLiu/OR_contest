from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd
from src.runtime import ROOT
from tools.audit_subsidy_results import audit


class SubsidyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        baseline = ROOT/'results/experiments/final-q2-subsidy-20261022'
        shutil.copytree(baseline/'question2', self.root/'question2')
        folder = self.root/'_runs/q2-subsidy'
        folder.mkdir(parents=True)
        shutil.copyfile(baseline/'_runs/q2-subsidy/solver_metrics.jsonl', folder/'solver_metrics.jsonl')

    def test_both_real_policies_reconcile(self):
        rows = audit(self.root)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row['issues'] for row in rows))
        self.assertEqual(rows[0]['subsidy'], 0)
        self.assertEqual(rows[1]['open_count'], 11)
        self.assertAlmostEqual(rows[1]['social_cost']-rows[1]['enterprise_cost'], 7)

    def test_false_subsidy_in_comparison_is_rejected(self):
        path = self.root/'question2/开仓补贴政策对比_cplex.csv'
        frame = pd.read_csv(path)
        frame.loc[1, '补贴金额（单位：万元）'] += 7
        frame.to_csv(path, index=False)
        self.assertTrue(audit(self.root)[1]['issues'])

    def test_false_procurement_is_rejected(self):
        path = self.root/'question2/subsidy_scenarios/with_subsidy/decisions.csv'
        frame = pd.read_csv(path)
        frame.loc[frame.smart.eq(1).idxmax(), 'smart'] = 0
        frame.to_csv(path, index=False)
        self.assertTrue(audit(self.root)[1]['issues'])

    def test_missing_counterfactual_is_not_success(self):
        (self.root/'question2/subsidy_scenarios/without_subsidy/flows.csv').unlink()
        with self.assertRaises(FileNotFoundError):
            audit(self.root)

    def test_nonfinite_comparison_is_rejected(self):
        path = self.root/'question2/开仓补贴政策对比_cplex.csv'
        frame = pd.read_csv(path)
        frame.loc[0, '补贴金额（单位：万元）'] = float('nan')
        frame.to_csv(path, index=False)
        with self.assertRaises(ValueError):
            audit(self.root)
