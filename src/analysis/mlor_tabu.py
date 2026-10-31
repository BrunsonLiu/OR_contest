"""Tabu search baseline under the same evaluation budget as the ALNS.

The neighborhood is all feasible relocations of a served store plus insertions
of an unserved store. The tabu attribute is (store, previous warehouse).
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import copy
import json

import src.analysis.mlor_alns as alnsmod
from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import CAPACITY, WAREHOUSES, make_instance, route_eval
from src.runtime import results_root


def feasible(warehouse_index, order, stores):
    if len(order) > CAPACITY:
        return False
    _, infeasible = route_eval(warehouse_index, order, stores, "actual")
    return infeasible == 0


def copy_routes(routes):
    return {w: [list(order) for order in route_list] for w, route_list in routes.items()}


def tabu_search(stores, budget, seed=0):
    routes = construct(stores, "actual", True)[1]
    served = {s for rl in routes.values() for order in rl for s in order}
    unserved = [s for s in range(len(stores)) if s not in served]
    current = solution_cost(routes, unserved, stores)
    best = current
    best_routes = copy_routes(routes)
    best_unserved = list(unserved)
    tabu = {}
    tenure = 7
    evaluations = 0
    iteration = 0
    while evaluations < budget:
        iteration += 1
        best_move = None
        best_move_cost = float("inf")
        # Relocations of served stores.
        for w, route_list in routes.items():
            for ri, order in enumerate(route_list):
                for pos, store in enumerate(order):
                    base = copy_routes(routes)
                    base[w][ri].pop(pos)
                    base[w] = [o for o in base[w] if o]
                    for w2 in range(len(WAREHOUSES)):
                        for r2 in range(len(base[w2]) + 1):
                            if r2 == len(base[w2]):
                                candidates = [[store]]
                            else:
                                candidates = [base[w2][r2][:p] + [store] + base[w2][r2][p:]
                                              for p in range(len(base[w2][r2]) + 1)]
                            for candidate in candidates:
                                evaluations += 1
                                if evaluations >= budget:
                                    break
                                if not feasible(w2, candidate, stores):
                                    continue
                                trial = copy_routes(base)
                                if r2 == len(trial[w2]):
                                    trial[w2].append(candidate)
                                else:
                                    trial[w2][r2] = candidate
                                cost = solution_cost(trial, unserved, stores)
                                if tabu.get((store, w), 0) > iteration and cost >= best:
                                    continue
                                if cost < best_move_cost:
                                    best_move_cost = cost
                                    best_move = (trial, list(unserved), store, w)
                            if evaluations >= budget:
                                break
                        if evaluations >= budget:
                            break
                    if evaluations >= budget:
                        break
                if evaluations >= budget:
                    break
            if evaluations >= budget:
                break
        # Insertions of unserved stores.
        if evaluations < budget:
            for store in unserved:
                for w2 in range(len(WAREHOUSES)):
                    for r2 in range(len(routes[w2]) + 1):
                        if r2 == len(routes[w2]):
                            candidates = [[store]]
                        else:
                            candidates = [routes[w2][r2][:p] + [store] + routes[w2][r2][p:]
                                          for p in range(len(routes[w2][r2]) + 1)]
                        for candidate in candidates:
                            evaluations += 1
                            if evaluations >= budget:
                                break
                            if not feasible(w2, candidate, stores):
                                continue
                            trial = copy_routes(routes)
                            if r2 == len(trial[w2]):
                                trial[w2].append(candidate)
                            else:
                                trial[w2][r2] = candidate
                            new_unserved = [s for s in unserved if s != store]
                            cost = solution_cost(trial, new_unserved, stores)
                            if cost < best_move_cost:
                                best_move_cost = cost
                                best_move = (trial, new_unserved, store, None)
                        if evaluations >= budget:
                            break
                    if evaluations >= budget:
                        break
                if evaluations >= budget:
                    break
        if best_move is None:
            break
        routes, unserved, tabu_store, old_warehouse = best_move
        current = best_move_cost
        if old_warehouse is not None:
            tabu[(tabu_store, old_warehouse)] = iteration + tenure
        if current < best:
            best = current
            best_routes = copy_routes(routes)
            best_unserved = list(unserved)
    return best, evaluations


def main():
    exact_path = _REPO_ROOT / "results/experiments/mlor-dp12-20261028/mlor_dp/summary.json"
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
        alns_best, _ = alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
        alnsmod.solution_cost = original
        tabu_best, evaluations = tabu_search(stores, calls[0], seed)
        rows.append({
            "seed": seed,
            "evaluations": evaluations,
            "alns": alns_best,
            "tabu": tabu_best,
            "exact": exact[seed],
            "alns_gap": alns_best - exact[seed],
            "tabu_gap": tabu_best - exact[seed],
        })
    summary = {
        "instances": len(rows),
        "alns_mean_gap": sum(row["alns_gap"] for row in rows) / len(rows),
        "tabu_mean_gap": sum(row["tabu_gap"] for row in rows) / len(rows),
        "alns_optimal": sum(1 for row in rows if abs(row["alns_gap"]) <= 1e-6),
        "tabu_optimal": sum(1 for row in rows if abs(row["tabu_gap"]) <= 1e-6),
        "alns_better": sum(1 for row in rows if row["alns"] < row["tabu"] - 1e-9),
        "tabu_better": sum(1 for row in rows if row["tabu"] < row["alns"] - 1e-9),
        "rows": rows,
        "scope": "twelve stores, three warehouses, equal solution-evaluation budget",
        "limitations": ["Tabu tenure is fixed at 7.", "Equal evaluations is only one fairness notion."],
    }
    out_dir = results_root() / "mlor_tabu"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "alns_mean_gap", "tabu_mean_gap", "alns_optimal", "tabu_optimal",
                       "alns_better", "tabu_better")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
