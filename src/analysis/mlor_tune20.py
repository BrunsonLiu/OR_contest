"""Twenty-store comparison of the default and larger ALNS destroy sizes."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.analysis.mlor_alns import alns
from src.analysis.mlor_scale import make_instance
from src.runtime import results_root


def main():
    rows = []
    for seed in range(10):
        stores = make_instance(seed, 20)
        default, _ = alns(stores, iterations=200, seed=seed)
        large, _ = alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
        rows.append({
            "seed": seed,
            "default": default,
            "destroy_4_6": large,
            "improvement": default - large,
        })
    summary = {
        "instances": len(rows),
        "large_better": sum(1 for row in rows if row["improvement"] > 1e-9),
        "default_better": sum(1 for row in rows if row["improvement"] < -1e-9),
        "mean_improvement": sum(row["improvement"] for row in rows) / len(rows),
        "rows": rows,
        "scope": "twenty stores, three warehouses, capacity four; destroy 2-4 versus 4-6",
        "limitations": [
            "No exact benchmark at twenty stores.",
            "Only the destroy size is varied.",
        ],
    }
    out_dir = results_root() / "mlor_tune20"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "large_better", "default_better", "mean_improvement")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
