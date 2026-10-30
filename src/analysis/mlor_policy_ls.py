"""Stronger baseline: freshest-feasible policy plus 2-opt and relocate search."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_policy import policy_solution
from src.analysis.mlor_scale import (
    CAPACITY, OPEN_COST, PENALTY, WAREHOUSES, make_instance, route_eval,
)
from src.runtime import results_root


def total_cost(routes, unserved):
    total = PENALTY * len(unserved)
    for warehouse_index, route_list in routes.items():
        if route_list:
            total += OPEN_COST
        for order in route_list:
            cost, _ = route_eval(warehouse_index, order, stores_ref[0], "actual")
            total += cost
    return total


def feasible(warehouse_index, order):
    if len(order) > CAPACITY:
        return False
    _, infeasible = route_eval(warehouse_index, order, stores_ref[0], "actual")
    return infeasible == 0


stores_ref = [None]


def local_search(routes, unserved, max_moves=200):
    current_routes = {w: [list(order) for order in route_list] for w, route_list in routes.items()}
    for _ in range(max_moves):
        current = total_cost(current_routes, unserved)
        best_delta = 0.0
        best_routes = None
        for warehouse_index, route_list in current_routes.items():
            for route_index, order in enumerate(route_list):
                for i in range(len(order) - 1):
                    for j in range(i + 2, len(order) + 1):
                        candidate = order[:i] + list(reversed(order[i:j])) + order[j:]
                        if not feasible(warehouse_index, candidate):
                            continue
                        trial = {w: [list(r) for r in rl] for w, rl in current_routes.items()}
                        trial[warehouse_index][route_index] = candidate
                        delta = total_cost(trial, unserved) - current
                        if delta < best_delta - 1e-9:
                            best_delta = delta
                            best_routes = trial
        served = [(w, ri, pos, store) for w, rl in current_routes.items()
                  for ri, order in enumerate(rl) for pos, store in enumerate(order)]
        for w, ri, pos, store in served:
            base = {ww: [list(r) for r in rr] for ww, rr in current_routes.items()}
            base[w][ri].pop(pos)
            base[w] = [order for order in base[w] if order]
            for w2 in range(len(WAREHOUSES)):
                for r2 in range(len(base[w2]) + 1):
                    if r2 == len(base[w2]):
                        candidates = [[store]]
                    else:
                        candidates = [base[w2][r2][:p2] + [store] + base[w2][r2][p2:]
                                      for p2 in range(len(base[w2][r2]) + 1)]
                    for candidate in candidates:
                        if not feasible(w2, candidate):
                            continue
                        trial = {ww: [list(r) for r in rr] for ww, rr in base.items()}
                        if r2 == len(base[w2]):
                            trial[w2].append(candidate)
                        else:
                            trial[w2][r2] = candidate
                        delta = total_cost(trial, unserved) - current
                        if delta < best_delta - 1e-9:
                            best_delta = delta
                            best_routes = trial
        if best_routes is None:
            break
        current_routes = best_routes
    return current_routes


def exact_costs(n_stores):
    name = "mlor-dp-20261028" if n_stores == 8 else "mlor-dp12-20261028"
    path = _REPO_ROOT / "results/experiments" / name / "mlor_dp/summary.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    return {row["seed"]: row["aware_cost"] for row in rows}


def main():
    summary = {"by_size": {}, "scope": "freshest policy plus 2-opt and relocate versus exact",
               "limitations": ["Synthetic instances.", "Local search uses the same age-feasibility check."]}
    for n_stores in (8, 12):
        exact = exact_costs(n_stores)
        gaps = []
        for seed in range(10):
            stores = make_instance(seed, n_stores)
            stores_ref[0] = stores
            _, _, routes = policy_solution(stores, "freshest")
            served = {s for rl in routes.values() for order in rl for s in order}
            unserved = [s for s in range(len(stores)) if s not in served]
            improved = local_search(routes, unserved)
            gaps.append(total_cost(improved, unserved) - exact[seed])
        summary["by_size"][str(n_stores)] = {
            "mean_gap": sum(gaps) / len(gaps),
            "max_gap": max(gaps),
            "optimal": sum(1 for gap in gaps if abs(gap) <= 1e-6),
            "gaps": gaps,
        }
    out_dir = results_root() / "mlor_policy_ls"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["by_size"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
