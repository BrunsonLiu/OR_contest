"""Hold-out tuning protocol for the MLOR ALNS.

The destroy size is selected on development seeds 0-4 and evaluated on test
seeds 5-14, all against the exact 12-store DP.
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
    "default_2_4": {"iterations": 200},
    "destroy_1_2": {"iterations": 200, "destroy_min": 1, "destroy_max": 2},
    "destroy_4_6": {"iterations": 200, "destroy_min": 4, "destroy_max": 6},
    "destroy_6_8": {"iterations": 200, "destroy_min": 6, "destroy_max": 8},
}


def load_exact():
    dev_path = _REPO_ROOT / "results/experiments/mlor-dp12-20261028/mlor_dp/summary.json"
    ext_path = _REPO_ROOT / "results/experiments/mlor-dp12-ext-20261031/mlor_dp/summary.json"
    dev_rows = json.loads(dev_path.read_text(encoding="utf-8"))["rows"]
    ext_rows = json.loads(ext_path.read_text(encoding="utf-8"))["rows"]
    exact = {row["seed"]: row["aware_cost"] for row in dev_rows}
    exact.update({row["seed"]: row["aware_cost"] for row in ext_rows})
    return exact


def gaps(seeds, exact, setting):
    values = []
    for seed in seeds:
        stores = make_instance(seed, 12)
        best, _ = alns(stores, seed=seed, **setting)
        values.append(best - exact[seed])
    return values


def main():
    exact = load_exact()
    development = list(range(5))
    test = list(range(5, 15))
    dev_results = {}
    for name, setting in SETTINGS.items():
        values = gaps(development, exact, setting)
        dev_results[name] = {
            "mean_gap": sum(values) / len(values),
            "optimal": sum(1 for gap in values if abs(gap) <= 1e-6),
            "gaps": values,
        }
    selected = min(SETTINGS, key=lambda name: dev_results[name]["mean_gap"])
    test_results = {}
    for name in ("default_2_4", selected):
        if name in test_results:
            continue
        values = gaps(test, exact, SETTINGS[name])
        test_results[name] = {
            "mean_gap": sum(values) / len(values),
            "max_gap": max(values),
            "optimal": sum(1 for gap in values if abs(gap) <= 1e-6),
            "gaps": values,
        }
    summary = {
        "protocol": "select destroy size on seeds 0-4; evaluate on seeds 5-14",
        "development": dev_results,
        "selected": selected,
        "test": test_results,
        "scope": "twelve stores, three warehouses, capacity four; exact DP reference",
        "limitations": ["Single synthetic instance family."],
    }
    out_dir = results_root() / "mlor_holdout"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({"selected": selected, "development": dev_results, "test": test_results}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
