"""Mechanism ablation for the MLOR problem: age x MLOR, 2x2.

Four configurations: age+MLOR (original), MLOR only (fresh warehouses), age
only (zero thresholds), neither. Age-aware planning is compared with a blind
plan that ignores both age and MLOR and is then evaluated under the
configuration's real ages and thresholds.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from itertools import permutations

from src.analysis.mlor_scale import (
    CAPACITY, COST_PER_KM, KM_PER_DAY, OPEN_COST, PENALTY, SHELF_LIFE,
    VEHICLE_COST, WAREHOUSES, distance, make_instance,
)
from src.runtime import results_root

INF = float("inf")
ORIGINAL_AGES = [warehouse["age"] for warehouse in WAREHOUSES]
FRESH_AGES = [0.0, 0.0, 0.0]
CONFIGS = {
    "age+mlor": (ORIGINAL_AGES, True),
    "mlor_only": (FRESH_AGES, True),
    "age_only": (ORIGINAL_AGES, False),
    "neither": (FRESH_AGES, False),
}


def route_cost(warehouse_index, order, stores, ages, age_actual, use_mlor):
    age = ages[warehouse_index] if age_actual else 0.0
    t = 0.0
    previous = WAREHOUSES[warehouse_index]["point"]
    cost = VEHICLE_COST
    infeasible = 0
    for store in order:
        leg = distance(previous, (stores[store]["x"], stores[store]["y"])) / KM_PER_DAY
        t += leg
        cost += leg * KM_PER_DAY * COST_PER_KM
        threshold = stores[store]["mlor"] if use_mlor else 0.0
        if SHELF_LIFE - age - t < threshold - 1e-9:
            infeasible += 1
        previous = (stores[store]["x"], stores[store]["y"])
    if order:
        leg = distance(previous, WAREHOUSES[warehouse_index]["point"]) / KM_PER_DAY
        cost += leg * KM_PER_DAY * COST_PER_KM
    return cost, infeasible


def best_routes(stores, ages, age_actual, use_mlor):
    routes = {index: [] for index in range(len(WAREHOUSES))}
    for warehouse_index in range(len(WAREHOUSES)):
        for subset in range(1, 1 << len(stores)):
            if bin(subset).count("1") > CAPACITY:
                continue
            indices = [index for index in range(len(stores)) if subset & (1 << index)]
            choice = None
            for order in permutations(indices):
                cost, infeasible = route_cost(warehouse_index, order, stores, ages, age_actual, use_mlor)
                if infeasible > 0:
                    continue
                if choice is None or cost < choice[0]:
                    choice = (cost, list(order))
            if choice is not None:
                routes[warehouse_index].append((subset, choice[0], choice[1]))
    return routes


def solve(routes, n_stores):
    full = (1 << n_stores) - 1
    dp = {(0, 0): 0.0}
    choice = {}
    for mask in range(1 << n_stores):
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
                    candidate = value + cost + (0.0 if already_open else OPEN_COST)
                    key = (new_mask, new_open)
                    if candidate < dp.get(key, INF) - 1e-9:
                        dp[key] = candidate
                        choice[key] = (mask, open_mask, warehouse_index, subset)
    best_open = None
    best = INF
    for (mask, open_mask), value in dp.items():
        if mask == full and value < best:
            best = value
            best_open = open_mask
    chosen = []
    key = (full, best_open)
    while key in choice:
        mask, open_mask, warehouse_index, subset = choice[key]
        chosen.append((warehouse_index, subset))
        key = (mask, open_mask)
    return best, chosen


def main():
    aggregate = {name: [] for name in CONFIGS}
    for seed in range(5):
        stores = make_instance(seed)
        blind_routes = best_routes(stores, FRESH_AGES, False, False)
        blind_planned, blind_chosen = solve(blind_routes, len(stores))
        for name, (ages, use_mlor) in CONFIGS.items():
            aware, _ = solve(best_routes(stores, ages, True, use_mlor), len(stores))
            infeasible = 0
            for warehouse_index, subset in blind_chosen:
                order = next(order for sub, _, order in blind_routes[warehouse_index] if sub == subset)
                _, count = route_cost(warehouse_index, order, stores, ages, True, use_mlor)
                infeasible += count
            blind_actual = blind_planned + PENALTY * infeasible
            aggregate[name].append(blind_actual - aware)
    summary = {
        "instances": 5,
        "configs": {},
        "scope": "eight stores, three warehouses, capacity four, exact subset DP; synthetic",
        "limitations": [
            "The blind plan is a single route set per seed, evaluated under each configuration.",
            "Synthetic parameters.",
        ],
    }
    for name, gaps in aggregate.items():
        summary["configs"][name] = {
            "mean_gap": sum(gaps) / len(gaps),
            "aware_better": sum(1 for gap in gaps if gap > 1e-9),
        }
    out_dir = results_root() / "mlor_mechanism"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["configs"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
