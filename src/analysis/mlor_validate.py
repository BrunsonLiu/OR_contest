"""Validate the age-aware ALNS against the exact 12-store subset DP."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
from pathlib import Path

from src.analysis.mlor_alns import alns, construct, solution_cost
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root


def main():
    reference = _REPO_ROOT / "results/experiments/mlor-dp12-r2-20261031/mlor_dp/summary.json"
    rows = json.loads(reference.read_text(encoding="utf-8"))["rows"]
    output = []
    for seed in range(10):
        stores = make_instance(seed, 12)
        _, routes, _ = construct(stores, "actual", True)
        served = {store for route_list in routes.values() for order in route_list for store in order}
        unserved = [store for store in range(len(stores)) if store not in served]
        initial = solution_cost(routes, unserved, stores)
        best, _ = alns(stores, iterations=200, seed=seed)
        optimum = rows[seed]["aware_cost"]
        output.append({
            "seed": seed,
            "initial": initial,
            "alns": best,
            "exact": optimum,
            "gap_to_exact": best - optimum,
            "relative_gap": (best - optimum) / optimum if optimum else None,
        })
    summary = {
        "instances": len(output),
        "optimal": sum(1 for row in output if abs(row["gap_to_exact"]) <= 1e-6),
        "mean_gap": sum(row["gap_to_exact"] for row in output) / len(output),
        "max_gap": max(row["gap_to_exact"] for row in output),
        "mean_relative_gap": sum(row["relative_gap"] for row in output) / len(output),
        "rows": output,
        "scope": "twelve stores, three warehouses, capacity four; ALNS versus exact subset DP",
        "limitations": [
            "Same synthetic instances as mlor-dp12.",
            "ALNS has no tuning or ablation here.",
        ],
    }
    out_dir = results_root() / "mlor_validate"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "optimal", "mean_gap", "max_gap", "mean_relative_gap")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
