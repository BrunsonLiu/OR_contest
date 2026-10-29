"""Network-design comparison for the MLOR problem.

Checks whether age-aware and age-blind plans open different warehouses and
assign stores differently, at 8 and 12 stores.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_mechanism import (
    FRESH_AGES, ORIGINAL_AGES, best_routes, route_cost, solve,
)
from src.analysis.mlor_scale import PENALTY, make_instance
from src.runtime import results_root


def analyse(stores):
    n = len(stores)
    aware_cost, aware_chosen = solve(best_routes(stores, ORIGINAL_AGES, True, True), n)
    blind_routes = best_routes(stores, FRESH_AGES, False, False)
    blind_planned, blind_chosen = solve(blind_routes, n)
    infeasible = 0
    for warehouse_index, subset in blind_chosen:
        order = next(order for sub, _, order in blind_routes[warehouse_index] if sub == subset)
        _, count = route_cost(warehouse_index, order, stores, ORIGINAL_AGES, True, True)
        infeasible += count
    blind_actual = blind_planned + PENALTY * infeasible
    open_aware = sorted({warehouse_index for warehouse_index, _ in aware_chosen})
    open_blind = sorted({warehouse_index for warehouse_index, _ in blind_chosen})
    assign_aware = {store: warehouse_index for warehouse_index, subset in aware_chosen
                    for store in range(n) if subset & (1 << store)}
    assign_blind = {store: warehouse_index for warehouse_index, subset in blind_chosen
                    for store in range(n) if subset & (1 << store)}
    return {
        "open_aware": open_aware,
        "open_blind": open_blind,
        "open_differs": open_aware != open_blind,
        "assignment_differs": assign_aware != assign_blind,
        "aware_cost": aware_cost,
        "blind_actual": blind_actual,
        "gap": aware_cost - blind_actual,
        "blind_infeasible": infeasible,
    }


def main():
    rows = []
    for n_stores in (8, 12):
        for seed in range(10):
            stores = make_instance(seed, n_stores)
            result = analyse(stores)
            result.update({"n_stores": n_stores, "seed": seed})
            rows.append(result)
    summary = {
        "instances": len(rows),
        "by_size": {},
        "rows": rows,
        "scope": "eight and twelve stores, three warehouses, capacity four; exact subset DP",
        "limitations": [
            "Synthetic instances.",
            "Only three warehouses, one of which is fresh.",
        ],
    }
    for n_stores in (8, 12):
        subset = [row for row in rows if row["n_stores"] == n_stores]
        summary["by_size"][str(n_stores)] = {
            "open_differs": sum(1 for row in subset if row["open_differs"]),
            "assignment_differs": sum(1 for row in subset if row["assignment_differs"]),
            "aware_opens_0": sum(1 for row in subset if row["open_aware"] == [0]),
            "blind_opens_0": sum(1 for row in subset if row["open_blind"] == [0]),
            "blind_infeasible_total": sum(row["blind_infeasible"] for row in subset),
            "mean_gap": sum(row["gap"] for row in subset) / len(subset),
        }
    out_dir = results_root() / "mlor_network"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["by_size"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
