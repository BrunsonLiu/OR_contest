import unittest

from src.analysis.live_scale import (
    edd, exact, fifo, make_instance, marginal, run, worst_state,
)


class LiveScaleTests(unittest.TestCase):
    def test_exact_is_never_below_the_rules(self):
        for seed in range(10):
            deadlines, multipliers, initial = make_instance(seed)
            optimum = exact(deadlines, multipliers, initial)
            for rule in (fifo, worst_state, edd, marginal):
                value = run(rule, deadlines, multipliers, initial)
                self.assertGreaterEqual(optimum + 1e-9, value)

    def test_exact_usually_beats_fifo(self):
        wins = 0
        for seed in range(20):
            deadlines, multipliers, initial = make_instance(seed)
            optimum = exact(deadlines, multipliers, initial)
            if optimum > run(fifo, deadlines, multipliers, initial) + 1e-9:
                wins += 1
        self.assertGreaterEqual(wins, 15)

    def test_marginal_is_close_to_exact(self):
        gaps = []
        for seed in range(20):
            deadlines, multipliers, initial = make_instance(seed)
            gaps.append(exact(deadlines, multipliers, initial) - run(marginal, deadlines, multipliers, initial))
        self.assertLessEqual(sum(gaps) / len(gaps), 0.1)


if __name__ == "__main__":
    unittest.main()
