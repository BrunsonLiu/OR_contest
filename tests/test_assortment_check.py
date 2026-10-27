import unittest

from src.analysis.assortment_check import SKUS, best_design


class AssortmentCheckTests(unittest.TestCase):
    def test_no_confirmation_cost_keeps_the_near_narrow_design(self):
        design = best_design(0.0)
        self.assertEqual((design["warehouse"], design["breadth"]), ("near", 0))

    def test_high_confirmation_cost_switches_to_broad_far_design(self):
        design = best_design(5.0)
        self.assertEqual((design["warehouse"], design["breadth"]), ("far", SKUS))

    def test_breadth_is_never_out_of_range(self):
        for cost in (0.0, 1.0, 3.0, 10.0):
            design = best_design(cost)
            self.assertGreaterEqual(design["breadth"], 0)
            self.assertLessEqual(design["breadth"], SKUS)


if __name__ == "__main__":
    unittest.main()
