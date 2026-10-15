import itertools
import unittest

import numpy as np
import pandas as pd

from src.backtesting import evaluate_windows, rolling_splits, seasonal_naive
from src.timeliness import worst_service_ratio


class BacktestTests(unittest.TestCase):
    def test_windows_and_short_history(self):
        self.assertEqual(rolling_splits(23), [(7, 14), (10, 17), (13, 20), (16, 23)])
        with self.assertRaises(ValueError):
            rolling_splits(13)

    def test_predictors_receive_only_past_and_fresh_state(self):
        dates = pd.date_range("2016-06-01", periods=23)
        values = np.tile(np.arange(23) % 7 + 1, (2, 1))
        frame = pd.DataFrame({"Name": ["a", "b"], "SKU": ["dm", "im"], "future_secret": [9, 9]})
        calls = []

        def factory():
            used = []

            def predict(keys, history, training_dates, targets):
                self.assertFalse(used)
                used.append(True)
                self.assertEqual(list(keys), ["Name", "SKU"])
                self.assertLess(training_dates[-1], targets[0])
                np.testing.assert_array_equal(history, values[:, :len(training_dates)])
                calls.append(len(training_dates))
                return seasonal_naive(keys, history, training_dates, targets)
            return predict

        report = evaluate_windows(frame, dates, values, {"weekly": factory}, rolling_splits(23))
        self.assertEqual(calls, [7, 10, 13, 16])
        self.assertEqual(report["summary"]["weekly"]["forecast_event_rmse"], 0)
        self.assertEqual(report["target_date_events_per_series"], 28)
        self.assertEqual(report["distinct_target_dates"], 16)

    def test_bad_predictions_and_empty_methods(self):
        dates = pd.date_range("2016-06-01", periods=14)
        frame = pd.DataFrame({"Name": ["a"], "SKU": ["dm"]})
        for predicted in (np.full((1, 7), np.nan), np.full((1, 7), -1), np.ones((7, 1))):
            with self.assertRaises(ValueError):
                evaluate_windows(frame, dates, np.ones((1, 14)), {"bad": lambda: lambda *args: predicted}, [(7, 14)])
        with self.assertRaises(ValueError):
            evaluate_windows(frame, dates, np.ones((1, 14)), {}, [(7, 14)])


class TimelinessTests(unittest.TestCase):
    def test_late_demand_reduces_ratio(self):
        result = worst_service_ratio([95, 5], [0, 10], [1, 0], .5)
        self.assertAlmostEqual(result["worst_ratio"], 95/105)

    def test_fractional_lp_matches_budget_vertices(self):
        nominal, delta = np.array([2., 5., 3.]), np.array([4., 1., 2.])
        for timely in itertools.product([0, 1], repeat=3):
            for budget in (0., .5, 1., 1.5, 3.):
                vertices = []
                for point in itertools.product([0., 1.], repeat=3):
                    if sum(point) <= budget:
                        vertices.append(np.array(point))
                    for axis in range(3):
                        candidate = np.array(point)
                        candidate[axis] = budget-sum(point)+point[axis]
                        if 0 <= candidate[axis] <= 1:
                            vertices.append(candidate)
                expected = min((nominal+delta*z) @ timely/(nominal+delta*z).sum() for z in vertices)
                self.assertAlmostEqual(worst_service_ratio(nominal, delta, timely, budget)["worst_ratio"], expected)

    def test_invalid_inputs(self):
        for nominal, delta, timely, budget in (([0], [1], [1], 1), ([1], [-1], [1], 1),
                                              ([1], [1], [2], 1), ([1], [1], [1], -1)):
            with self.assertRaises(ValueError):
                worst_service_ratio(nominal, delta, timely, budget)
