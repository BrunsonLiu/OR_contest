"""ALNS parameter sensitivity for the MLOR problem at twelve stores.

Varies the iteration budget and the destroy size, and compares each setting
with the exact subset DP. The default setting is 200 iterations, destroy 2-4.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_alns import alns
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root

SETTINGS = {
    "iter_50": {"iterations": 50},
    "iter_100": {"iterations": 100},
    "iter_200": {"iterations": 200},
    "iter_400": {"iterations": 400},
    "destroy_1_2": {"iterations": 200, "destroy_min": 1, "destroy_max": 2},
    "destroy_2_4": {"iterations": 200},
    "destroy_4_6": {"iterations": 200, "destroy_min": 4, "destroy_max": 6},
}


def main():
    reference = _REPO_ROOT / "results/experiments/mlor-dp12-20261028/mlor_dp/summary.json"
    exact_rows = json.loads(reference.read_text(encoding="utf-8"))["rows"]
    results = {name: [] for name in SETTINGS}
    for seed in range(10):
        stores = make_instance(seed, 12)
        exact = exact_rows[seed]["aware_cost"]
        for name, kwargs in SETTINGS.items():
            best, _ = alns(stores, seed=seed, **kwargs)
            results[name].append(best - exact)
    summary = {
        "instances": 10,
        "settings": {},
        "scope": "twelve stores, three warehouses, capacity four; ALNS settings against exact DP",
        "limitations": [
            "One synthetic instance family.",
            "Only iteration budget and destroy size are varied.",
        ],
    }
    for name, gaps in results.items():
        summary["settings"][name] = {
            "mean_gap": sum(gaps) / len(gaps),
            "max_gap": max(gaps),
            "optimal": sum(1 for gap in gaps if abs(gap) <= 1e-6),
        }
    out_dir = results_root() / "mlor_tuning"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps(summary["settings"], ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
