"""Twenty-store main result with the tuned destroy size (4-6)."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root


def unserved_list(stores, routes):
    served = {store for route_list in routes.values() for order in route_list for store in order}
    return [store for store in range(len(stores)) if store not in served]


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed, 20)
        routes = construct(stores, "actual", True)[1]
        initial = solution_cost(routes, unserved_list(stores, routes), stores)
        best, _ = alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
        rows.append({
            "seed": seed,
            "initial": initial,
            "tuned": best,
            "improvement": initial - best,
        })
    summary = {
        "instances": len(rows),
        "improved": sum(1 for row in rows if row["improvement"] > 1e-6),
        "mean_improvement": sum(row["improvement"] for row in rows) / len(rows),
        "rows": rows,
        "scope": "twenty stores, three warehouses, capacity four; ALNS with destroy 4-6 against greedy",
        "limitations": [
            "No exact benchmark at twenty stores.",
            "The tuned setting is not uniformly better than the default; see mlor-tune20-20261028.",
        ],
    }
    out_dir = results_root() / "mlor_alns_large"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "improved", "mean_improvement")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
