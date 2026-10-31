"""Robustness of nominal age-aware and age-blind plans to warehouse age error.

The plans are not re-optimized. Each scenario shifts each warehouse age by an
independent uniform draw in [-0.5, 0.5] days and evaluates both plans.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import random

from src.analysis.mlor_alns import alns, solution_cost
from src.analysis.mlor_scale import WAREHOUSES, construct, evaluate, make_instance
from src.runtime import results_root

SCENARIOS = 50
SHIFT = 0.5


def unserved_of(routes, stores):
    served = {store for route_list in routes.values() for order in route_list for store in order}
    return [store for store in range(len(stores)) if store not in served]


def shifted(routes, unserved, stores, deltas):
    old = [warehouse["age"] for warehouse in WAREHOUSES]
    try:
        for warehouse, delta in zip(WAREHOUSES, deltas):
            warehouse["age"] = warehouse["age"] + delta
        cost = solution_cost(routes, unserved, stores)
        _, violations = evaluate(routes, stores, "actual", len(unserved))
        return cost, violations
    finally:
        for warehouse, age in zip(WAREHOUSES, old):
            warehouse["age"] = age


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed, 12)
        aware_cost, aware_routes, aware_unserved = alns(
            stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6, return_routes=True)
        _, blind_routes, _ = construct(stores, "blind", False)
        blind_unserved = unserved_of(blind_routes, stores)
        rng = random.Random(seed * 1000 + 7)
        aware_costs, blind_costs = [], []
        aware_violations, blind_violations = [], []
        for _ in range(SCENARIOS):
            deltas = [rng.uniform(-SHIFT, SHIFT) for _ in WAREHOUSES]
            aware_value, aware_count = shifted(aware_routes, aware_unserved, stores, deltas)
            blind_value, blind_count = shifted(blind_routes, blind_unserved, stores, deltas)
            aware_costs.append(aware_value)
            blind_costs.append(blind_value)
            aware_violations.append(aware_count)
            blind_violations.append(blind_count)
        wins = sum(1 for aware, blind in zip(aware_costs, blind_costs) if aware < blind - 1e-9)
        rows.append({
            "seed": seed,
            "aware_nominal": aware_cost,
            "blind_nominal": solution_cost(blind_routes, blind_unserved, stores),
            "aware_mean": sum(aware_costs) / SCENARIOS,
            "blind_mean": sum(blind_costs) / SCENARIOS,
            "aware_wins": wins,
            "scenarios": SCENARIOS,
            "aware_violations": sum(aware_violations) / SCENARIOS,
            "blind_violations": sum(blind_violations) / SCENARIOS,
        })
    summary = {
        "instances": len(rows),
        "scenarios_per_instance": SCENARIOS,
        "age_shift_days": SHIFT,
        "aware_mean": sum(row["aware_mean"] for row in rows) / len(rows),
        "blind_mean": sum(row["blind_mean"] for row in rows) / len(rows),
        "aware_win_rate": sum(row["aware_wins"] for row in rows) / (len(rows) * SCENARIOS),
        "aware_violations": sum(row["aware_violations"] for row in rows) / len(rows),
        "blind_violations": sum(row["blind_violations"] for row in rows) / len(rows),
        "rows": rows,
        "scope": "twelve stores, nominal plans not re-optimized, warehouse age uncertainty only",
        "limitations": ["Travel time and demand are deterministic.",
                        "The age shift is symmetric and independent across warehouses."],
    }
    out_dir = results_root() / "mlor_robustness"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "aware_mean", "blind_mean", "aware_win_rate",
                       "aware_violations", "blind_violations")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
