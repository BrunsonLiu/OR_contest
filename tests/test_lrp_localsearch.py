import unittest

from src.analysis.lrp_localsearch import (
    evaluate, joint, local_search, make_instance, repair, sequential,
)


class LrpLocalSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stores = make_instance(0)
        cls.stores = stores
        seq = repair(sequential(stores), stores)
        jnt = joint(stores)
        cls.seq_final = local_search(seq, stores) if seq else None
        cls.jnt_final = local_search(jnt, stores) if jnt else None

    def test_both_initial_solutions_reach_feasibility(self):
        self.assertIsNotNone(self.seq_final)
        self.assertIsNotNone(self.jnt_final)
        self.assertLessEqual(evaluate(self.seq_final[1], self.stores)[1], 0.05 + 1e-9)
        self.assertLessEqual(evaluate(self.jnt_final[1], self.stores)[1], 0.05 + 1e-9)

    def test_joint_is_not_worse_on_the_first_instance(self):
        self.assertLessEqual(self.jnt_final[0], self.seq_final[0] + 1e-6)

    def test_local_search_never_increases_cost(self):
        seq = repair(sequential(self.stores), self.stores)
        before = evaluate(seq, self.stores)[0]
        after = local_search(seq, self.stores)[0]
        self.assertLessEqual(after, before + 1e-6)


if __name__ == "__main__":
    unittest.main()
