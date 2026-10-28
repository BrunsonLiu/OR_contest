"""Sensitivity of the MLOR value to the store rejection penalty.

Eight stores, exact subset DP. The age-aware cost is independent of the
penalty because it is always feasible; the age-blind plan pays the penalty for
every infeasible delivery. Illustrative parameters only.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_dp2 import best_routes, route_cost, solve
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root

PENALTIES = (0.0, 50.0, 100.0, 200.0, 400.0, 800.0)


def main():
    per_penalty = {penalty: [] for penalty in PENALTIES}
    for seed in range(5):
        stores = make_instance(seed)
        aware, _ = solve(best_routes(stores, "actual", True))
        blind_routes = best_routes(stores, "zero", False)
        blind_planned, chosen = solve(blind_routes)
        infeasible = 0
        for warehouse_index, subset in chosen:
            order = next(order for sub, _, order in blind_routes[warehouse_index] if sub == subset)
            _, count = route_cost(warehouse_index, order, stores, "actual")
            infeasible += count
        for penalty in PENALTIES:
            blind_actual = blind_planned + penalty * infeasible
            per_penalty[penalty].append({
                "seed": seed,
                "aware": aware,
                "blind_planned": blind_planned,
                "blind_actual": blind_actual,
                "gap": blind_actual - aware,
            })
    summary = {
        "instances": 5,
        "penalties": {},
        "scope": "eight stores, three warehouses, capacity four, exact subset DP; synthetic",
        "limitations": [
            "Single synthetic instance family.",
            "Penalty is a modelling parameter, not an observed markdown cost.",
        ],
    }
    for penalty, rows in per_penalty.items():
        summary["penalties"][str(penalty)] = {
            "mean_gap": sum(row["gap"] for row in rows) / len(rows),
            "aware_better": sum(1 for row in rows if row["gap"] > 1e-9),
        }
    out_dir = results_root() / "mlor_sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["penalties"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
