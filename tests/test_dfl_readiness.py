import unittest

import pandas as pd

from src.analysis.assess_dfl_readiness import window_inventory


class DflReadinessTests(unittest.TestCase):
    def test_weekly_labels_do_not_leak_into_holdout(self):
        report = window_inventory(pd.date_range("2016-06-01", periods=23))
        self.assertEqual(report["case_counts"], {
            "pre_holdout": 3, "crosses_holdout": 6, "within_holdout": 1})
        self.assertEqual(report["maximum_nonoverlapping_pre_holdout_target_blocks"], 1)
        training = [w for w in report["windows"] if w["role"] == "pre_holdout"]
        self.assertEqual([w["target_end"] for w in training],
                         ["2016-06-14", "2016-06-15", "2016-06-16"])
        for window in report["windows"]:
            self.assertLess(window["history_end"], window["target_start"])
            if window["role"] == "pre_holdout":
                self.assertLess(window["target_end"], report["holdout_start"])
            elif window["role"] == "within_holdout":
                self.assertGreaterEqual(window["target_start"], report["holdout_start"])

    def test_daily_is_a_different_problem_with_only_nine_pre_holdout_days(self):
        report = window_inventory(pd.date_range("2016-06-01", periods=23), horizon=1)
        self.assertEqual(report["case_counts"], {
            "pre_holdout": 9, "crosses_holdout": 0, "within_holdout": 7})
        self.assertEqual(report["maximum_nonoverlapping_pre_holdout_target_blocks"], 9)
        self.assertFalse(report["validation_reserved_within_pre_holdout"])

    def test_reject_missing_unordered_or_short_dates_and_invalid_lengths(self):
        dates = pd.date_range("2016-06-01", periods=23)
        for invalid in (dates.delete(4), dates[::-1], dates[:13], dates.insert(2, dates[2])):
            with self.assertRaises(ValueError):
                window_inventory(invalid)
        for kwargs in ({"horizon": 0}, {"min_history": -1}, {"holdout_days": 1.5}):
            with self.assertRaises(ValueError):
                window_inventory(dates, **kwargs)

    def test_no_training_week_when_only_history_and_holdout_exist(self):
        report = window_inventory(pd.date_range("2016-06-01", periods=14))
        self.assertEqual(report["case_counts"], {
            "pre_holdout": 0, "crosses_holdout": 0, "within_holdout": 1})


if __name__ == "__main__":
    unittest.main()
