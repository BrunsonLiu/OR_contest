"""Medium MLOR-aware cold-chain LRP check.

Three warehouses with different inventory ages, ten stores with different
minimum remaining shelf life (MLOR), up to two routes per warehouse with
capacity three. An age-aware insertion heuristic is compared with an age-blind
one that ignores age. Illustrative parameters only.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import random

from src.runtime import results_root

WAREHOUSES = [
    {"name": "W0", "point": (150.0, 150.0), "age": 0.0},
    {"name": "W1", "point": (100.0, 100.0), "age": 2.5},
    {"name": "W2", "point": (200.0, 200.0), "age": 4.5},
]
N_STORES = 8
CAPACITY = 4
ROUTES_PER_WAREHOUSE = 2
SHELF_LIFE = 6.0
OPEN_COST = 100.0
VEHICLE_COST = 50.0
COST_PER_KM = 0.5
PENALTY = 200.0
KM_PER_DAY = 100.0


def make_instance(seed):
    rng = random.Random(seed)
    stores = []
    for _ in range(N_STORES):
        stores.append({"x": rng.uniform(0, 300), "y": rng.uniform(0, 300), "mlor": rng.choice([1.0, 2.0, 3.0])})
    return stores


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def route_eval(warehouse_index, order, stores, age_mode):
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


def construct(stores, age_mode, enforce_mlor):
    routes = {index: [] for index in range(len(WAREHOUSES))}
    total = 0.0
    unserved = 0
    for store in sorted(range(len(stores)), key=lambda index: -stores[index]["mlor"]):
        best = None
        for warehouse_index in range(len(WAREHOUSES)):
            for route_index, order in enumerate(routes[warehouse_index]):
                if len(order) >= CAPACITY:
                    continue
                old_cost, old_inf = route_eval(warehouse_index, order, stores, age_mode)
                for position in range(len(order) + 1):
                    candidate = order[:position] + [store] + order[position:]
                    cost, infeasible = route_eval(warehouse_index, candidate, stores, age_mode)
                    if enforce_mlor and infeasible > 0:
                        continue
                    delta = cost - old_cost
                    if best is None or delta < best[0]:
                        best = (delta, warehouse_index, route_index, candidate)
            if len(routes[warehouse_index]) < ROUTES_PER_WAREHOUSE:
                cost, infeasible = route_eval(warehouse_index, [store], stores, age_mode)
                if enforce_mlor and infeasible > 0:
                    continue
                extra = OPEN_COST if not routes[warehouse_index] else 0.0
                if best is None or cost + extra < best[0]:
                    best = (cost + extra, warehouse_index, None, [store])
        if best is None:
            total += PENALTY
            unserved += 1
            continue
        delta, warehouse_index, route_index, candidate = best
        if route_index is None:
            routes[warehouse_index].append(candidate)
        else:
            routes[warehouse_index][route_index] = candidate
        total += delta
    return total, routes, unserved


def evaluate(routes, stores, age_mode, unserved=0):
    total = 0.0
    infeasible = 0
    for warehouse_index, route_list in routes.items():
        if route_list:
            total += OPEN_COST
        for order in route_list:
            cost, route_infeasible = route_eval(warehouse_index, order, stores, age_mode)
            total += cost
            infeasible += route_infeasible
    return total + PENALTY * unserved, infeasible + unserved


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed)
        aware_cost, aware_routes, aware_unserved = construct(stores, "actual", True)
        aware_actual, aware_inf = evaluate(aware_routes, stores, "actual", aware_unserved)
        blind_cost, blind_routes, blind_unserved = construct(stores, "zero", False)
        blind_actual, blind_inf = evaluate(blind_routes, stores, "actual", blind_unserved)
        rows.append({
            "seed": seed,
            "aware_planned": aware_cost,
            "aware_actual": aware_actual,
            "aware_infeasible": aware_inf,
            "aware_unserved": aware_unserved,
            "blind_planned": blind_cost,
            "blind_actual": blind_actual,
            "blind_infeasible": blind_inf,
            "blind_unserved": blind_unserved,
            "gap": aware_actual - blind_actual,
        })
    summary = {
        "instances": len(rows),
        "aware_better": sum(1 for row in rows if row["gap"] < -1e-9),
        "blind_better": sum(1 for row in rows if row["gap"] > 1e-9),
        "mean_gap": sum(row["gap"] for row in rows) / len(rows),
        "aware_infeasible_total": sum(row["aware_infeasible"] for row in rows),
        "blind_infeasible_total": sum(row["blind_infeasible"] for row in rows),
        "rows": rows,
        "scope": "three warehouses, ten stores, age 0/2.5/4.5, MLOR 1-3, two routes per warehouse, capacity three; synthetic",
        "limitations": [
            "Insertion heuristic, not an exact or ALNS comparison.",
            "Single product and single temperature zone.",
            "Cost and penalty parameters are illustrative.",
        ],
    }
    out_dir = results_root() / "mlor_scale"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "aware_better", "blind_better", "mean_gap",
                       "aware_infeasible_total", "blind_infeasible_total")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
