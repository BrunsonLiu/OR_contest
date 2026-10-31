"""Genetic algorithm baseline under the same evaluation budget as the ALNS."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import random

import src.analysis.mlor_alns as alnsmod
from src.analysis.mlor_alns import alns, construct, insert_best, solution_cost
from src.analysis.mlor_sa import neighbour
from src.analysis.mlor_scale import CAPACITY, WAREHOUSES, make_instance, route_eval
from src.runtime import results_root

POPULATION = 20


def feasible(warehouse_index, order, stores):
    if len(order) > CAPACITY:
        return False
    _, infeasible = route_eval(warehouse_index, order, stores, "actual")
    return infeasible == 0


def copy_routes(routes):
    return {w: [list(order) for order in route_list] for w, route_list in routes.items()}


def repair(routes, unserved, stores):
    unserved = list(unserved)
    for store in list(unserved):
        insertion = insert_best(routes, store, stores, True)
        if insertion is not None:
            routes = insertion[1]
            unserved.remove(store)
    return routes, unserved


def random_individual(stores, rng):
    routes = construct(stores, "actual", True)[1]
    served = {s for rl in routes.values() for order in rl for s in order}
    unserved = [s for s in range(len(stores)) if s not in served]
    for _ in range(rng.randint(1, 3)):
        trial = neighbour(routes, unserved, stores, rng)
        if trial is not None:
            routes, unserved = trial
    routes, unserved = repair(routes, unserved, stores)
    return {"routes": copy_routes(routes), "unserved": list(unserved)}


def crossover(a, b, stores, rng):
    routes = {w: [] for w in range(len(WAREHOUSES))}
    assigned = set()
    for w in range(len(WAREHOUSES)):
        for order in a["routes"][w]:
            if rng.random() < 0.5:
                routes[w].append(list(order))
                assigned.update(order)
    unserved = []
    for w in range(len(WAREHOUSES)):
        for order in b["routes"][w]:
            remaining = [s for s in order if s not in assigned]
            if not remaining:
                continue
            if feasible(w, remaining, stores):
                routes[w].append(remaining)
                assigned.update(remaining)
            else:
                unserved.extend(remaining)
    for store in list(a["unserved"]) + list(b["unserved"]):
        if store not in assigned and store not in unserved:
            unserved.append(store)
    routes, unserved = repair(routes, unserved, stores)
    return {"routes": routes, "unserved": unserved}


def mutate(individual, stores, rng):
    routes = copy_routes(individual["routes"])
    unserved = list(individual["unserved"])
    for _ in range(rng.randint(1, 2)):
        trial = neighbour(routes, unserved, stores, rng)
        if trial is not None:
            routes, unserved = trial
    return {"routes": routes, "unserved": unserved}


def genetic(stores, budget, seed=0):
    rng = random.Random(seed)
    population = []
    evaluations = 0
    for _ in range(POPULATION):
        individual = random_individual(stores, rng)
        individual["cost"] = solution_cost(individual["routes"], individual["unserved"], stores)
        evaluations += 1
        population.append(individual)
    best = min(population, key=lambda x: x["cost"])
    while evaluations < budget:
        new_population = [best]
        while len(new_population) < POPULATION and evaluations < budget:
            def tournament():
                picks = rng.sample(population, 3)
                return min(picks, key=lambda x: x["cost"])
            child = crossover(tournament(), tournament(), stores, rng)
            child = mutate(child, stores, rng)
            child["cost"] = solution_cost(child["routes"], child["unserved"], stores)
            evaluations += 1
            new_population.append(child)
            if child["cost"] < best["cost"]:
                best = child
        population = new_population
    return best["cost"], evaluations


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
        alns_best, _ = alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
        alnsmod.solution_cost = original
        ga_best, evaluations = genetic(stores, calls[0], seed)
        rows.append({"seed": seed, "evaluations": evaluations, "alns": alns_best, "ga": ga_best,
                     "exact": exact[seed], "alns_gap": alns_best - exact[seed], "ga_gap": ga_best - exact[seed]})
    summary = {
        "instances": len(rows),
        "alns_mean_gap": sum(row["alns_gap"] for row in rows) / len(rows),
        "ga_mean_gap": sum(row["ga_gap"] for row in rows) / len(rows),
        "alns_optimal": sum(1 for row in rows if abs(row["alns_gap"]) <= 1e-6),
        "ga_optimal": sum(1 for row in rows if abs(row["ga_gap"]) <= 1e-6),
        "alns_better": sum(1 for row in rows if row["alns"] < row["ga"] - 1e-9),
        "ga_better": sum(1 for row in rows if row["ga"] < row["alns"] - 1e-9),
        "rows": rows,
        "scope": "twelve stores, three warehouses, equal solution-evaluation budget",
        "limitations": ["GA is not tuned beyond population and tournament size.",
                        "Equal evaluations is only one fairness notion."],
    }
    out_dir = results_root() / "mlor_ga"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "alns_mean_gap", "ga_mean_gap", "alns_optimal", "ga_optimal",
                       "alns_better", "ga_better")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
