"""Scaled live-seafood recovery check.

Four batches, one recovery slot, five periods, heterogeneous deadlines and
transport multipliers. The exact DP is compared with FIFO, worst-state-first,
EDD, and a marginal-survival greedy. Illustrative parameters only.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import random
from functools import lru_cache

from src.runtime import results_root

SURVIVAL = (0.5, 0.8, 0.9)
N = 4
PERIODS = 5


def make_instance(seed):
    rng = random.Random(seed)
    deadlines = [rng.randint(2, 4) for _ in range(N)]
    multipliers = [round(rng.uniform(0.5, 1.0), 2) for _ in range(N)]
    initial = [rng.randint(0, 1) for _ in range(N)]
    return deadlines, multipliers, initial


def exact(deadlines, multipliers, initial):
    @lru_cache(maxsize=None)
    def best(t, xs, mask):
        xs = list(xs)
        value = 0.0
        for index in range(N):
            if mask & (1 << index) and t >= deadlines[index]:
                value += SURVIVAL[xs[index]] * multipliers[index]
                mask &= ~(1 << index)
        if t == PERIODS or mask == 0:
            return value
        options = [best(t + 1, tuple(xs), mask)]
        for index in range(N):
            if mask & (1 << index) and xs[index] < 2:
                updated = xs[:]
                updated[index] += 1
                options.append(best(t + 1, tuple(updated), mask))
        return value + max(options)

    return best(0, tuple(initial), (1 << N) - 1)


def run(rule, deadlines, multipliers, initial):
    xs = list(initial)
    mask = (1 << N) - 1
    value = 0.0
    for t in range(PERIODS):
        for index in range(N):
            if mask & (1 << index) and t >= deadlines[index]:
                value += SURVIVAL[xs[index]] * multipliers[index]
                mask &= ~(1 << index)
        if mask == 0:
            break
        index = rule(t, xs, mask, deadlines, multipliers)
        if index is not None:
            xs[index] = min(2, xs[index] + 1)
    return value


def fifo(t, xs, mask, deadlines, multipliers):
    for index in range(N):
        if mask & (1 << index) and xs[index] < 2:
            return index
    return None


def worst_state(t, xs, mask, deadlines, multipliers):
    candidates = [index for index in range(N) if mask & (1 << index) and xs[index] < 2]
    return min(candidates, key=lambda index: (xs[index], index)) if candidates else None


def edd(t, xs, mask, deadlines, multipliers):
    candidates = [index for index in range(N) if mask & (1 << index) and xs[index] < 2]
    return min(candidates, key=lambda index: (deadlines[index], index)) if candidates else None


def marginal(t, xs, mask, deadlines, multipliers):
    candidates = [index for index in range(N) if mask & (1 << index) and xs[index] < 2]
    if not candidates:
        return None
    return max(candidates, key=lambda index: ((SURVIVAL[xs[index] + 1] - SURVIVAL[xs[index]]) * multipliers[index],
                                              -deadlines[index]))


def main():
    rules = {"fifo": fifo, "worst_state": worst_state, "edd": edd, "marginal": marginal}
    rows = []
    for seed in range(20):
        deadlines, multipliers, initial = make_instance(seed)
        optimum = exact(deadlines, multipliers, initial)
        row = {"seed": seed, "exact": optimum,
               "deadlines": deadlines, "multipliers": multipliers, "initial": initial}
        for name, rule in rules.items():
            row[name] = run(rule, deadlines, multipliers, initial)
        rows.append(row)
    summary = {
        "instances": len(rows),
        "exact_beats_fifo": sum(1 for row in rows if row["exact"] > row["fifo"] + 1e-9),
        "exact_beats_worst": sum(1 for row in rows if row["exact"] > row["worst_state"] + 1e-9),
        "exact_beats_edd": sum(1 for row in rows if row["exact"] > row["edd"] + 1e-9),
        "exact_beats_marginal": sum(1 for row in rows if row["exact"] > row["marginal"] + 1e-9),
        "mean_gap_marginal": sum(row["exact"] - row["marginal"] for row in rows) / len(rows),
        "mean_gap_edd": sum(row["exact"] - row["edd"] for row in rows) / len(rows),
        "rows": rows,
        "scope": "four batches, one slot, five periods, heterogeneous deadlines and multipliers; synthetic",
        "limitations": [
            "Survival probabilities and multipliers are assumed.",
            "Dispatch is automatic at the deadline; no early dispatch or holding cost.",
            "Only one recovery slot and four batches.",
        ],
    }
    out_dir = results_root() / "live_scale"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "exact_beats_fifo", "exact_beats_worst", "exact_beats_edd",
                       "exact_beats_marginal", "mean_gap_marginal", "mean_gap_edd")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
