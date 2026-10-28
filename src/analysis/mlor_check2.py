"""Minimal MLOR-aware cold-chain LRP check (corrected instance).

Two warehouses, three stores, one route per warehouse with capacity two.
The old warehouse is next to a high-MLOR store but cannot deliver it within
the remaining-shelf-life threshold; the fresh warehouse can. An age-blind
plan is compared with an age-aware plan. Illustrative parameters only.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from itertools import permutations, product

from src.runtime import results_root

WAREHOUSES = [
    {"name": "W_fresh", "point": (0.0, 0.0), "age": 0.0},
    {"name": "W_old", "point": (100.0, 0.0), "age": 4.8},
]
STORES = [
    {"x": 110.0, "y": 0.0, "mlor": 1.0},
    {"x": 100.0, "y": 10.0, "mlor": 3.0},
    {"x": 0.0, "y": 10.0, "mlor": 1.0},
]
SHELF_LIFE = 6.0
CAPACITY = 2
OPEN_COST = 100.0
COST_PER_KM = 0.5
PENALTY = 200.0
KM_PER_DAY = 100.0


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def evaluate_plan(plan, age_mode):
    total = 0.0
    infeasible = 0
    for warehouse_index, order in plan.items():
        if not order:
            continue
        warehouse = WAREHOUSES[warehouse_index]
        age = warehouse["age"] if age_mode == "actual" else 0.0
        total += OPEN_COST
        t = 0.0
        previous = warehouse["point"]
        for store in order:
            leg = distance(previous, (STORES[store]["x"], STORES[store]["y"])) / KM_PER_DAY
            t += leg
            total += leg * KM_PER_DAY * COST_PER_KM
            remaining = SHELF_LIFE - age - t
            if remaining < STORES[store]["mlor"] - 1e-9:
                infeasible += 1
            previous = (STORES[store]["x"], STORES[store]["y"])
    return total + PENALTY * infeasible, infeasible


def all_plans():
    for assignment in product(range(len(WAREHOUSES)), repeat=len(STORES)):
        groups = {index: [] for index in range(len(WAREHOUSES))}
        for store, warehouse_index in enumerate(assignment):
            groups[warehouse_index].append(store)
        if any(len(group) > CAPACITY for group in groups.values()):
            continue
        options = [list(permutations(group)) if group else [()] for group in groups.values()]
        for orders in product(*options):
            yield {index: list(orders[index]) for index in range(len(WAREHOUSES))}


def best(age_mode, require_feasible):
    best_plan = None
    for plan in all_plans():
        cost, infeasible = evaluate_plan(plan, age_mode)
        if require_feasible and infeasible > 0:
            continue
        if best_plan is None or (cost, infeasible) < (best_plan[0], best_plan[1]):
            best_plan = (cost, infeasible, plan)
    return best_plan


def main():
    aware = best("actual", True)
    blind_planned = best("zero", False)
    blind_actual_cost, blind_infeasible = evaluate_plan(blind_planned[2], "actual")
    summary = {
        "shelf_life": SHELF_LIFE,
        "warehouses": WAREHOUSES,
        "stores": STORES,
        "age_aware_cost": aware[0],
        "age_aware_infeasible": aware[1],
        "age_aware_plan": {str(key): value for key, value in aware[2].items()},
        "age_blind_planned_cost": blind_planned[0],
        "age_blind_actual_cost": blind_actual_cost,
        "age_blind_infeasible": blind_infeasible,
        "age_blind_plan": {str(key): value for key, value in blind_planned[2].items()},
        "age_aware_better": aware[0] < blind_actual_cost - 1e-9,
        "scope": "two warehouses, three stores, one temperature zone, one route per warehouse, capacity two; synthetic",
        "limitations": [
            "Single product and single temperature zone.",
            "One inventory age per warehouse.",
            "Cost and penalty parameters are illustrative.",
        ],
    }
    out_dir = results_root() / "mlor_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("age_aware_cost", "age_blind_planned_cost", "age_blind_actual_cost", "age_aware_better")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
