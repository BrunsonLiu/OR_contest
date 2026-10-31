"""Practical policy baselines for the MLOR problem.

Three simple policies assign each store to a warehouse by a rule (nearest
feasible, freshest feasible, oldest feasible) and insert it greedily into that
warehouse's routes. They are compared with the exact age-aware optimum.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_scale import (
    CAPACITY, KM_PER_DAY, OPEN_COST, PENALTY, SHELF_LIFE, WAREHOUSES, distance,
    make_instance, route_eval,
)
from src.runtime import results_root

POLICIES = ("nearest", "freshest", "oldest")


def policy_solution(stores, mode):
    routes = {warehouse_index: [] for warehouse_index in range(len(WAREHOUSES))}
    unserved = []
    for store in sorted(range(len(stores)), key=lambda index: -stores[index]["mlor"]):
        point = (stores[store]["x"], stores[store]["y"])
        if mode == "nearest":
            candidates = sorted(range(len(WAREHOUSES)),
                                key=lambda w: distance(WAREHOUSES[w]["point"], point))
        elif mode == "freshest":
            candidates = sorted(range(len(WAREHOUSES)), key=lambda w: WAREHOUSES[w]["age"])
        else:
            candidates = sorted(range(len(WAREHOUSES)), key=lambda w: -WAREHOUSES[w]["age"])
        placed = False
        for warehouse_index in candidates:
            direct = distance(WAREHOUSES[warehouse_index]["point"], point) / KM_PER_DAY
            if SHELF_LIFE - WAREHOUSES[warehouse_index]["age"] - direct < stores[store]["mlor"] - 1e-9:
                continue
            best = None
            for route_index, order in enumerate(routes[warehouse_index]):
                if len(order) >= CAPACITY:
                    continue
                old_cost, _ = route_eval(warehouse_index, order, stores, "actual")
                for position in range(len(order) + 1):
                    candidate = order[:position] + [store] + order[position:]
                    cost, infeasible = route_eval(warehouse_index, candidate, stores, "actual")
                    if infeasible:
                        continue
                    delta = cost - old_cost
                    if best is None or delta < best[0]:
                        best = (delta, route_index, candidate)
            if best is not None:
                _, route_index, candidate = best
                routes[warehouse_index][route_index] = candidate
                placed = True
                break
            cost, infeasible = route_eval(warehouse_index, [store], stores, "actual")
            if infeasible == 0:
                routes[warehouse_index].append([store])
                placed = True
                break
        if not placed:
            unserved.append(store)
    total = 0.0
    for warehouse_index, route_list in routes.items():
        if route_list:
            total += OPEN_COST
        for order in route_list:
            cost, _ = route_eval(warehouse_index, order, stores, "actual")
            total += cost
    return total + PENALTY * len(unserved), len(unserved), routes


def exact_costs(n_stores, seeds):
    name = "mlor-dp-r2-20261031" if n_stores == 8 else "mlor-dp12-r2-20261031"
    path = _REPO_ROOT / "results/experiments" / name / "mlor_dp/summary.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    return {row["seed"]: row["aware_cost"] for row in rows if row["seed"] in seeds}


def main():
    summary = {"by_size": {}, "scope": "8/12 stores, exact optimum versus three practical policies",
               "limitations": ["Synthetic instances.", "Policies assign first, then insert greedily."]}
    for n_stores in (8, 12):
        seeds = set(range(10))
        exact = exact_costs(n_stores, seeds)
        result = {mode: {"gaps": [], "unserved": []} for mode in POLICIES}
        for seed in range(10):
            stores = make_instance(seed, n_stores)
            for mode in POLICIES:
                cost, unserved, _ = policy_solution(stores, mode)
                result[mode]["gaps"].append(cost - exact[seed])
                result[mode]["unserved"].append(unserved)
        summary["by_size"][str(n_stores)] = {
            mode: {
                "mean_gap": sum(values["gaps"]) / len(values["gaps"]),
                "max_gap": max(values["gaps"]),
                "optimal": sum(1 for gap in values["gaps"] if abs(gap) <= 1e-6),
                "unserved_total": sum(values["unserved"]),
            }
            for mode, values in result.items()
        }
    out_dir = results_root() / "mlor_policy"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["by_size"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
