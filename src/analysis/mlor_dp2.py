"""Exact subset DP for the medium MLOR comparison (complete version).

Eight stores, three warehouses, routes up to four stores. Age-aware routes must
respect every store's MLOR at arrival. Age-blind routes are chosen with age
zero and no MLOR check, then charged the real-age penalties.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from itertools import permutations

from src.analysis.mlor_scale import (
    CAPACITY, COST_PER_KM, KM_PER_DAY, N_STORES, OPEN_COST, PENALTY, SHELF_LIFE,
    VEHICLE_COST, WAREHOUSES, distance, make_instance,
)
from src.runtime import results_root

FULL = (1 << N_STORES) - 1
INF = float("inf")


def route_cost(warehouse_index, order, stores, age_mode):
    warehouse = WAREHOUSES[warehouse_index]
    age = warehouse["age"] if age_mode == "actual" else 0.0
    t = 0.0
    previous = warehouse["point"]
    cost = VEHICLE_COST
    infeasible = 0
    for store in order:
        leg = distance(previous, (stores[store]["x"], stores[store]["y"])) / KM_PER_DAY
        t += leg
        cost += leg * KM_PER_DAY * COST_PER_KM
        if SHELF_LIFE - age - t < stores[store]["mlor"] - 1e-9:
            infeasible += 1
        previous = (stores[store]["x"], stores[store]["y"])
    return cost, infeasible


def best_routes(stores, age_mode, enforce_mlor):
    routes = {index: [] for index in range(len(WAREHOUSES))}
    for warehouse_index in range(len(WAREHOUSES)):
        for subset in range(1, 1 << N_STORES):
            size = bin(subset).count("1")
            if size > CAPACITY:
                continue
            indices = [index for index in range(N_STORES) if subset & (1 << index)]
            choice = None
            for order in permutations(indices):
                cost, infeasible = route_cost(warehouse_index, order, stores, age_mode)
                if enforce_mlor and infeasible > 0:
                    continue
                if choice is None or cost < choice[0]:
                    choice = (cost, list(order))
            if choice is not None:
                routes[warehouse_index].append((subset, choice[0], choice[1]))
    return routes


def solve(routes):
    dp = {(0, 0): 0.0}
    choice = {}
    for mask in range(1 << N_STORES):
        for open_mask in range(1 << len(WAREHOUSES)):
            value = dp.get((mask, open_mask))
            if value is None:
                continue
            for warehouse_index in range(len(WAREHOUSES)):
                already_open = bool(open_mask & (1 << warehouse_index))
                for subset, cost, order in routes[warehouse_index]:
                    if subset & mask:
                        continue
                    new_mask = mask | subset
                    new_open = open_mask | (1 << warehouse_index)
                    extra = cost + (0.0 if already_open else OPEN_COST)
                    candidate = value + extra
                    key = (new_mask, new_open)
                    if candidate < dp.get(key, INF) - 1e-9:
                        dp[key] = candidate
                        choice[key] = (mask, open_mask, warehouse_index, subset)
    best_open = None
    best_cost = INF
    for (mask, open_mask), value in dp.items():
        if mask == FULL and value < best_cost:
            best_cost = value
            best_open = open_mask
    chosen = []
    key = (FULL, best_open)
    while key in choice:
        mask, open_mask, warehouse_index, subset = choice[key]
        chosen.append((warehouse_index, subset))
        key = (mask, open_mask)
    return best_cost, chosen


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed)
        aware_routes = best_routes(stores, "actual", True)
        blind_routes = best_routes(stores, "zero", False)
        aware_cost, _ = solve(aware_routes)
        blind_planned, blind_chosen = solve(blind_routes)
        infeasible = 0
        for warehouse_index, subset in blind_chosen:
            order = next(order for sub, _, order in blind_routes[warehouse_index] if sub == subset)
            _, count = route_cost(warehouse_index, order, stores, "actual")
            infeasible += count
        blind_actual = blind_planned + PENALTY * infeasible
        rows.append({
            "seed": seed,
            "aware_cost": aware_cost,
            "blind_planned": blind_planned,
            "blind_actual": blind_actual,
            "blind_infeasible": infeasible,
            "gap": aware_cost - blind_actual,
        })
    summary = {
        "instances": len(rows),
        "aware_better": sum(1 for row in rows if row["gap"] < -1e-9),
        "blind_better": sum(1 for row in rows if row["gap"] > 1e-9),
        "mean_gap": sum(row["gap"] for row in rows) / len(rows),
        "blind_infeasible_total": sum(row["blind_infeasible"] for row in rows),
        "rows": rows,
        "scope": "eight stores, three warehouses, capacity four, exact subset DP; synthetic",
        "limitations": [
            "Single product and single temperature zone.",
            "One route order per subset is chosen by minimum cost.",
            "Cost and penalty parameters are illustrative.",
        ],
    }
    out_dir = results_root() / "mlor_dp"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "aware_better", "blind_better", "mean_gap", "blind_infeasible_total")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
