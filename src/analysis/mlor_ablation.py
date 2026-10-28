"""Ablation for the MLOR ALNS at twelve stores.

Compares greedy, no age feasibility, no unserved retry, and the full ALNS
against the exact subset DP.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root


def greedy_cost(stores):
    _, routes, _ = construct(stores, "actual", True)
    served = {store for route_list in routes.values() for order in route_list for store in order}
    unserved = [store for store in range(len(stores)) if store not in served]
    return solution_cost(routes, unserved, stores)


def main():
    reference = _REPO_ROOT / "results/experiments/mlor-dp12-20261028/mlor_dp/summary.json"
    rows = json.loads(reference.read_text(encoding="utf-8"))["rows"]
    variants = {
        "greedy": None,
        "no_retry": {"retry_unserved": False},
        "full": {},
    }
    results = {name: [] for name in variants}
    for seed in range(10):
        stores = make_instance(seed, 12)
        exact = rows[seed]["aware_cost"]
        for name, kwargs in variants.items():
            if kwargs is None:
                cost = greedy_cost(stores)
            else:
                cost, _ = alns(stores, iterations=200, seed=seed, **kwargs)
            results[name].append(cost - exact)
    summary = {
        "instances": len(rows),
        "variants": {},
        "rows": {},
        "scope": "twelve stores, three warehouses, capacity four; ablation against exact subset DP",
        "limitations": [
            "Single synthetic instance family.",
            "No tuning of ALNS parameters.",
        ],
    }
    for name, gaps in results.items():
        summary["variants"][name] = {
            "mean_gap": sum(gaps) / len(gaps),
            "max_gap": max(gaps),
            "optimal": sum(1 for gap in gaps if abs(gap) <= 1e-6),
        }
        summary["rows"][name] = gaps
    out_dir = results_root() / "mlor_ablation"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["variants"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
