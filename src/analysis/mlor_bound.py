"""LP lower bound for the 20-store MLOR instance.

Enumerate age-feasible routes of up to four stores per warehouse, then solve
the LP relaxation of the set-partitioning model (fractional routes, fractional
opening). Compare with the age-aware ALNS cost.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from itertools import combinations, permutations

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from src.analysis.mlor_alns import alns
from src.analysis.mlor_scale import (
    CAPACITY, OPEN_COST, WAREHOUSES, make_instance, route_eval,
)
from src.runtime import results_root


def routes_for(stores):
    columns = []
    for warehouse_index in range(len(WAREHOUSES)):
        for size in range(1, CAPACITY + 1):
            for subset in combinations(range(len(stores)), size):
                best = None
                for order in permutations(subset):
                    cost, infeasible = route_eval(warehouse_index, list(order), stores, "actual")
                    if infeasible == 0 and (best is None or cost < best[0]):
                        best = (cost, list(order))
                if best is not None:
                    columns.append((warehouse_index, best[0], subset))
    return columns


def lp_bound(stores, columns):
    n_stores = len(stores)
    n_columns = len(columns)
    n_warehouses = len(WAREHOUSES)
    c = np.array([column[1] for column in columns] + [OPEN_COST] * n_warehouses)

    eq_rows, eq_cols, eq_data = [], [], []
    for column_index, (_, _, subset) in enumerate(columns):
        for store in subset:
            eq_rows.append(store)
            eq_cols.append(column_index)
            eq_data.append(1.0)
    a_eq = coo_matrix((eq_data, (eq_rows, eq_cols)), shape=(n_stores, n_columns + n_warehouses)).tocsr()
    b_eq = np.ones(n_stores)

    ub_rows, ub_cols, ub_data = [], [], []
    for column_index, (warehouse_index, _, _) in enumerate(columns):
        ub_rows.extend([column_index, column_index])
        ub_cols.extend([column_index, n_columns + warehouse_index])
        ub_data.extend([1.0, -1.0])
    a_ub = coo_matrix((ub_data, (ub_rows, ub_cols)),
                      shape=(n_columns, n_columns + n_warehouses)).tocsr()
    b_ub = np.zeros(n_columns)

    result = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                     bounds=[(0, 1)] * (n_columns + n_warehouses), method="highs")
    if not result.success:
        return None, result.message
    return result.fun, "ok"


def main():
    rows = []
    for seed in range(5):
        stores = make_instance(seed, 20)
        columns = routes_for(stores)
        bound, message = lp_bound(stores, columns)
        cost, _ = alns(stores, iterations=200, seed=seed)
        rows.append({
            "seed": seed,
            "routes": len(columns),
            "lp_bound": bound,
            "alns": cost,
            "relative_gap": None if bound in (None, 0) else (cost - bound) / bound,
            "lp_message": message,
        })
    valid = [row for row in rows if row["lp_bound"] is not None]
    summary = {
        "instances": len(rows),
        "valid": len(valid),
        "mean_relative_gap": sum(row["relative_gap"] for row in valid) / len(valid) if valid else None,
        "max_relative_gap": max((row["relative_gap"] for row in valid), default=None),
        "rows": rows,
        "scope": "twenty stores, three warehouses, capacity four; LP relaxation versus ALNS",
        "limitations": [
            "LP relaxation is weak: fractional routes and fractional opening are allowed.",
            "ALNS cost includes penalties for any unserved stores; the LP assumes all stores served.",
        ],
    }
    out_dir = results_root() / "mlor_bound"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "valid", "mean_relative_gap", "max_relative_gap")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
