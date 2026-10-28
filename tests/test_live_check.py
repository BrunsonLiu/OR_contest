import unittest

from src.analysis.live_check import edd, exact, fifo, worst_state_first


class LiveCheckTests(unittest.TestCase):
    def test_exact_value(self):
        self.assertAlmostEqual(exact(), 1.28, places=6)

    def test_exact_beats_the_three_rules(self):
        best = exact()
        for rule in (fifo(), worst_state_first(), edd()):
            self.assertGreater(best, rule[0] + 1e-9)

    def test_rules_recover_the_first_arrival_twice(self):
        self.assertEqual(fifo()[1], [0, 2])
        self.assertAlmostEqual(fifo()[0], 1.04, places=6)


if __name__ == "__main__":
    unittest.main()
