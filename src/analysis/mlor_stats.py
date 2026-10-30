"""Confidence intervals for the MLOR comparisons."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import math

from scipy.stats import t

from src.runtime import results_root


def ci(values):
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return {"n": n, "mean": mean, "sd": None, "ci95": None}
    variance = sum((value - mean) ** 2 for value in values) / (n - 1)
    sd = math.sqrt(variance)
    half = t.ppf(0.975, n - 1) * sd / math.sqrt(n)
    return {"n": n, "mean": mean, "sd": sd, "ci95": [mean - half, mean + half]}


def load(rel):
    return json.loads((_REPO_ROOT / "results/experiments" / rel).read_text(encoding="utf-8"))


def main():
    dp8 = load("mlor-dp-20261028/mlor_dp/summary.json")["rows"]
    dp12 = load("mlor-dp12-20261028/mlor_dp/summary.json")["rows"]
    holdout = load("mlor-holdout2-20261031/mlor_holdout2/summary.json")
    policy_ls = load("mlor-policy-ls-20261031/mlor_policy_ls/summary.json")
    tuned = holdout["test"]["destroy_4_6"]["gaps"]
    default = holdout["test"]["default_2_4"]["gaps"]
    paired = [d - t for d, t in zip(default, tuned)]
    stats = {
        "holdout_paired_default_minus_tuned": ci(paired),
        "exact_advantage_8": ci([-row["gap"] for row in dp8]),
        "exact_advantage_12": ci([-row["gap"] for row in dp12]),
        "alns_holdout_4_6_gap": ci(holdout["test"]["destroy_4_6"]["gaps"]),
        "alns_holdout_default_gap": ci(holdout["test"]["default_2_4"]["gaps"]),
        "policy_ls_gap_8": ci(policy_ls["by_size"]["8"]["gaps"]),
        "policy_ls_gap_12": ci(policy_ls["by_size"]["12"]["gaps"]),
    }
    out_dir = results_root() / "mlor_stats"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    for name, value in stats.items():
        print(name, "mean", round(value["mean"], 3), "CI", [round(x, 3) for x in value["ci95"]])
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
