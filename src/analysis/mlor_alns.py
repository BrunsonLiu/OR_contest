"""Age-aware ALNS for the MLOR cold-chain LRP at twenty stores.

Destroy a few stores and reinsert them at the cheapest age-feasible position
across warehouses and routes. The initial solution is the greedy age-aware
insertion. Illustrative parameters only.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import copy
import json
import random

from src.analysis.mlor_scale import (
    CAPACITY, OPEN_COST, PENALTY, WAREHOUSES, construct, evaluate, make_instance, route_eval,
)
from src.runtime import results_root  # noqa: E402


def solution_cost(routes, unserved, stores=None):
    if stores is not None:
        STORES_REF[0] = stores
    total = 0.0
    infeasible = 0
    for warehouse_index, route_list in routes.items():
        if route_list:
            total += OPEN_COST
        for order in route_list:
            route_cost, count = route_eval(warehouse_index, order, STORES_REF[0], "actual")
            total += route_cost
            infeasible += count
    return total + PENALTY * (infeasible + len(unserved))


STORES_REF = [None]


def insert_best(routes, store, stores, enforce_age=True):
    best = None
    for warehouse_index in range(len(WAREHOUSES)):
        for route_index, order in enumerate(routes[warehouse_index]):
            if len(order) >= CAPACITY:
                continue
            for position in range(len(order) + 1):
                candidate = order[:position] + [store] + order[position:]
                _, infeasible = route_eval(warehouse_index, candidate, stores, "actual")
                if enforce_age and infeasible:
                    continue
                trial = copy.deepcopy(routes)
                trial[warehouse_index][route_index] = candidate
                cost = solution_cost(trial, [])
                if best is None or cost < best[0]:
                    best = (cost, trial)
        if len(routes[warehouse_index]) < 6:
            _, infeasible = route_eval(warehouse_index, [store], stores, "actual")
            if not enforce_age or infeasible == 0:
                trial = copy.deepcopy(routes)
                trial[warehouse_index].append([store])
                cost = solution_cost(trial, [])
                if best is None or cost < best[0]:
                    best = (cost, trial)
    return best


def alns(stores, iterations=300, seed=0, enforce_age=True, retry_unserved=True,
         destroy_min=2, destroy_max=4, extra_min=2, extra_max=2):
    STORES_REF[0] = stores
    rng = random.Random(seed)
    _, initial_routes, _ = construct(stores, "actual", enforce_age)
    served_initial = {store for route_list in initial_routes.values() for order in route_list for store in order}
    initial_unserved = [store for store in range(len(stores)) if store not in served_initial]
    best_routes = copy.deepcopy(initial_routes)
    best_unserved = list(initial_unserved)
    best_cost = solution_cost(best_routes, best_unserved)
    current_routes = copy.deepcopy(best_routes)
    current_unserved = list(best_unserved)
    current_cost = best_cost
    for _ in range(iterations):
        trial_routes = copy.deepcopy(current_routes)
        trial_unserved = list(current_unserved)
        served = [(w, store) for w, route_list in trial_routes.items() for order in route_list for store in order]
        if len(served) < 3:
            break
        removed = rng.sample(served, min(rng.randint(destroy_min, destroy_max), len(served)))
        for warehouse_index, store in removed:
            for order in trial_routes[warehouse_index]:
                if store in order:
                    order.remove(store)
            trial_routes[warehouse_index] = [order for order in trial_routes[warehouse_index] if order]
        if retry_unserved and trial_unserved:
            if extra_min == 2 and extra_max == 2:
                extra_count = min(2, len(trial_unserved))
            else:
                extra_count = min(rng.randint(extra_min, extra_max), len(trial_unserved))
            extra = rng.sample(trial_unserved, extra_count)
        else:
            extra = []
        trial_unserved = [store for store in trial_unserved if store not in extra]
        pool = [store for _, store in removed] + extra
        rng.shuffle(pool)
        for store in pool:
            insertion = insert_best(trial_routes, store, stores, enforce_age)
            if insertion is None:
                trial_unserved.append(store)
            else:
                trial_routes = insertion[1]
        trial_cost = solution_cost(trial_routes, trial_unserved)
        if trial_cost < current_cost - 1e-9:
            current_routes = trial_routes
            current_unserved = trial_unserved
            current_cost = trial_cost
            if trial_cost < best_cost - 1e-9:
                best_routes = copy.deepcopy(trial_routes)
                best_unserved = list(trial_unserved)
                best_cost = trial_cost
    return best_cost, initial_cost(initial_routes, initial_unserved)


def initial_cost(routes, unserved):
    return solution_cost(routes, unserved)


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed, 20)
        _, initial_routes, _ = construct(stores, "actual", enforce_age)
        served_initial = {store for route_list in initial_routes.values() for order in route_list for store in order}
        initial_unserved = [store for store in range(len(stores)) if store not in served_initial]
        initial = solution_cost(initial_routes, initial_unserved, stores)
        best, _ = alns(stores, iterations=200, seed=seed)
        rows.append({"seed": seed, "initial": initial, "alns": best, "improvement": initial - best})
    summary = {
        "instances": len(rows),
        "improved": sum(1 for row in rows if row["improvement"] > 1e-6),
        "mean_improvement": sum(row["improvement"] for row in rows) / len(rows),
        "rows": rows,
        "scope": "twenty stores, three warehouses, capacity four, age-aware ALNS; synthetic",
        "limitations": [
            "No exact benchmark at twenty stores.",
            "Greedy initial solution; simple destroy-repair.",
            "Cost parameters are illustrative.",
        ],
    }
    out_dir = results_root() / "mlor_alns"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "improved", "mean_improvement")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
