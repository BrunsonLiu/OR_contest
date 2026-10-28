import unittest

from src.analysis.lrp_check import assignment_cost, best_for


class LrpCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.direct = best_for(allow_pairing=False, require_service=True)
        cls.joint = best_for(allow_pairing=True, require_service=True)

    def test_both_strategies_are_feasible(self):
        self.assertIsNotNone(self.direct)
        self.assertIsNotNone(self.joint)

    def test_joint_is_not_worse_than_direct(self):
        self.assertLessEqual(self.joint["cost"], self.direct["cost"] + 1e-6)

    def test_joint_is_not_worse_than_sequential(self):
        sequential = assignment_cost(self.direct["open"], self.direct["assignment"], True, False)
        self.assertIsNotNone(sequential)
        self.assertLessEqual(self.joint["cost"], sequential[0] + 1e-6)

    def test_only_the_small_far_store_is_late(self):
        late = sorted(store for store, on_time in self.joint["on_time"].items() if not on_time)
        self.assertEqual(late, [3])

    def test_routing_changes_the_assignment(self):
        self.assertNotEqual(self.direct["assignment"], self.joint["assignment"])


if __name__ == "__main__":
    unittest.main()
