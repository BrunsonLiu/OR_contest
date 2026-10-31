"""Simulated annealing baseline under the same evaluation budget as the ALNS.

The ALNS evaluation count is measured by wrapping solution_cost; the SA then
receives the same number of solution evaluations. The comparison is indicative
because the two methods use different neighborhoods.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import math
import random
import time

import src.analysis.mlor_alns as alnsmod
from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import (
    CAPACITY, OPEN_COST, PENALTY, WAREHOUSES, make_instance, route_eval,
)
from src.runtime import results_root


def copy_routes(routes):
    return {w: [list(order) for order in route_list] for w, route_list in routes.items()}


def feasible(warehouse_index, order, stores):
    if len(order) > CAPACITY:
        return False
    _, infeasible = route_eval(warehouse_index, order, stores, "actual")
    return infeasible == 0


def neighbour(routes, unserved, stores, rng):
    routes = copy_routes(routes)
    unserved = list(unserved)
    served = [(w, ri, pos) for w, rl in routes.items() for ri, order in enumerate(rl) for pos in range(len(order))]
    move = rng.choice(["relocate", "swap", "two_opt", "insert_unserved"])
    if move == "relocate" and served:
        w, ri, pos = rng.choice(served)
        store = routes[w][ri].pop(pos)
        routes[w] = [order for order in routes[w] if order]
        w2 = rng.randrange(len(WAREHOUSES))
        r2 = rng.randrange(len(routes[w2]) + 1)
        if r2 == len(routes[w2]):
            candidate = [store]
        else:
            p2 = rng.randrange(len(routes[w2][r2]) + 1)
            candidate = routes[w2][r2][:p2] + [store] + routes[w2][r2][p2:]
        if not feasible(w2, candidate, stores):
            return None
        if r2 == len(routes[w2]):
            routes[w2].append(candidate)
        else:
            routes[w2][r2] = candidate
    elif move == "swap" and len(served) >= 2:
        (w1, r1, p1), (w2, r2, p2) = rng.sample(served, 2)
        routes[w1][r1][p1], routes[w2][r2][p2] = routes[w2][r2][p2], routes[w1][r1][p1]
        if not feasible(w1, routes[w1][r1], stores) or not feasible(w2, routes[w2][r2], stores):
            return None
    elif move == "two_opt" and served:
        w, ri, _ = rng.choice(served)
        order = routes[w][ri]
        if len(order) < 2:
            return None
        i = rng.randrange(len(order) - 1)
        j = rng.randrange(i + 2, len(order) + 1)
        candidate = order[:i] + list(reversed(order[i:j])) + order[j:]
        if not feasible(w, candidate, stores):
            return None
        routes[w][ri] = candidate
    elif move == "insert_unserved" and unserved:
        store = rng.choice(unserved)
        unserved.remove(store)
        w = rng.randrange(len(WAREHOUSES))
        r = rng.randrange(len(routes[w]) + 1)
        if r == len(routes[w]):
            candidate = [store]
        else:
            p = rng.randrange(len(routes[w][r]) + 1)
            candidate = routes[w][r][:p] + [store] + routes[w][r][p:]
        if not feasible(w, candidate, stores):
            return None
        if r == len(routes[w]):
            routes[w].append(candidate)
        else:
            routes[w][r] = candidate
    else:
        return None
    return routes, unserved


def sa(stores, budget, seed):
    rng = random.Random(seed)
    routes = construct(stores, "actual", True)[1]
    served = {s for rl in routes.values() for order in rl for s in order}
    unserved = [s for s in range(len(stores)) if s not in served]
    current = solution_cost(routes, unserved, stores)
    best = current
    best_routes = copy_routes(routes)
    best_unserved = list(unserved)
    temperature = 0.05 * max(current, 1.0)
    cooling = (1e-3) ** (1.0 / max(budget, 1))
    for _ in range(budget):
        trial = neighbour(routes, unserved, stores, rng)
        if trial is None:
            temperature *= cooling
            continue
        trial_routes, trial_unserved = trial
        trial_cost = solution_cost(trial_routes, trial_unserved, stores)
        delta = trial_cost - current
        if delta < 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            routes, unserved, current = trial_routes, trial_unserved, trial_cost
            if current < best:
                best = current
                best_routes = copy_routes(routes)
                best_unserved = list(unserved)
        temperature *= cooling
    return best, best_routes, best_unserved


def main():
    exact_path = _REPO_ROOT / "results/experiments/mlor-dp12-r2-20261031/mlor_dp/summary.json"
    exact = {row["seed"]: row["aware_cost"] for row in json.loads(exact_path.read_text(encoding="utf-8"))["rows"]}
    rows = []
    for seed in range(10):
        stores = make_instance(seed, 12)
        calls = [0]
        original = alnsmod.solution_cost
        def counted(routes, unserved, stores_arg=None):
            calls[0] += 1
            return original(routes, unserved, stores_arg)
        alnsmod.solution_cost = counted
        start = time.perf_counter()
        alns_best, _ = alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
        alns_time = time.perf_counter() - start
        alnsmod.solution_cost = original
        start = time.perf_counter()
        sa_best, _, _ = sa(stores, calls[0], seed)
        sa_time = time.perf_counter() - start
        rows.append({
            "seed": seed,
            "evaluations": calls[0],
            "alns": alns_best,
            "sa": sa_best,
            "exact": exact[seed],
            "alns_gap": alns_best - exact[seed],
            "sa_gap": sa_best - exact[seed],
            "alns_time": alns_time,
            "sa_time": sa_time,
        })
    summary = {
        "instances": len(rows),
        "alns_mean_gap": sum(row["alns_gap"] for row in rows) / len(rows),
        "sa_mean_gap": sum(row["sa_gap"] for row in rows) / len(rows),
        "alns_optimal": sum(1 for row in rows if abs(row["alns_gap"]) <= 1e-6),
        "sa_optimal": sum(1 for row in rows if abs(row["sa_gap"]) <= 1e-6),
        "alns_better": sum(1 for row in rows if row["alns"] < row["sa"] - 1e-9),
        "sa_better": sum(1 for row in rows if row["sa"] < row["alns"] - 1e-9),
        "rows": rows,
        "scope": "twelve stores, three warehouses, equal solution-evaluation budget",
        "limitations": [
            "SA is not tuned beyond a geometric cooling schedule.",
            "Different neighborhoods; equal evaluations is only one fairness notion.",
        ],
    }
    out_dir = results_root() / "mlor_sa"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "alns_mean_gap", "sa_mean_gap", "alns_optimal", "sa_optimal",
                       "alns_better", "sa_better")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
