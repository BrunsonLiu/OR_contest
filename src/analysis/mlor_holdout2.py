"""Cleaner hold-out protocol: select on seeds 5-9, test on seeds 10-19."""
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


def rows(path):
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def main():
    base = _REPO_ROOT / "results/experiments"
    dp12 = {row["seed"]: row["aware_cost"]
            for row in rows(base / "mlor-dp12-20261028/mlor_dp/summary.json")}
    ext = {row["seed"]: row["aware_cost"]
           for row in rows(base / "mlor-dp12-ext-20261031/mlor_dp/summary.json")}
    ext2 = {row["seed"]: row["aware_cost"]
            for row in rows(base / "mlor-dp12-ext2-20261031/mlor_dp/summary.json")}
    exact = {**dp12, **ext, **ext2}
    development = list(range(5, 10))
    test = list(range(10, 20))

    def evaluate(seeds, setting):
        values = []
        for seed in seeds:
            stores = make_instance(seed, 12)
            best, _ = alns(stores, seed=seed, **setting)
            values.append(best - exact[seed])
        return values

    dev = {}
    for name, setting in SETTINGS.items():
        values = evaluate(development, setting)
        dev[name] = {"mean_gap": sum(values) / len(values),
                     "optimal": sum(1 for gap in values if abs(gap) <= 1e-6),
                     "gaps": values}
    selected = min(SETTINGS, key=lambda name: dev[name]["mean_gap"])
    test_results = {}
    for name in ("default_2_4", selected):
        if name in test_results:
            continue
        values = evaluate(test, SETTINGS[name])
        test_results[name] = {"mean_gap": sum(values) / len(values),
                              "max_gap": max(values),
                              "optimal": sum(1 for gap in values if abs(gap) <= 1e-6),
                              "gaps": values}
    summary = {
        "protocol": "select destroy size on seeds 5-9; evaluate on seeds 10-19",
        "development": dev,
        "selected": selected,
        "test": test_results,
        "scope": "twelve stores, three warehouses, capacity four; exact DP reference",
        "limitations": ["Single synthetic instance family."],
    }
    out_dir = results_root() / "mlor_holdout2"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({"selected": selected, "development": dev, "test": test_results}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
