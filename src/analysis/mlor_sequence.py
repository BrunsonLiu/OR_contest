"""Test whether MLOR-descending order is feasible whenever some order is.

If counterexamples exist, no simple threshold-sorting rule is valid and the
route-feasibility subproblem genuinely depends on the sequence.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import itertools
import json
import random

from src.analysis.mlor_scale import WAREHOUSES, make_instance, route_eval
from src.runtime import results_root


def main():
    rng = random.Random(0)
    checked = 0
    violations = 0
    examples = []
    for seed in range(5):
        stores = make_instance(seed, 12)
        for warehouse_index in range(len(WAREHOUSES)):
            subsets = list(itertools.combinations(range(len(stores)), 3)) + \
                list(itertools.combinations(range(len(stores)), 4))
            for subset in rng.sample(subsets, min(30, len(subsets))):
                feasible = False
                for order in itertools.permutations(subset):
                    _, infeasible = route_eval(warehouse_index, list(order), stores, "actual")
                    if infeasible == 0:
                        feasible = True
                        break
                if not feasible:
                    continue
                checked += 1
                descending = tuple(sorted(subset, key=lambda store: -stores[store]["mlor"]))
                _, infeasible = route_eval(warehouse_index, list(descending), stores, "actual")
                if infeasible > 0:
                    violations += 1
                    if len(examples) < 3:
                        examples.append({
                            "seed": seed,
                            "warehouse": warehouse_index,
                            "subset": list(subset),
                            "descending": list(descending),
                        })
    summary = {
        "checked": checked,
        "violations": violations,
        "examples": examples,
        "scope": "twelve stores, random subsets of size 3-4, exact permutation check",
        "conclusion": "MLOR-descending order is not generally feasible when some order is; sequence matters.",
    }
    out_dir = results_root() / "mlor_sequence"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({"checked": checked, "violations": violations}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
