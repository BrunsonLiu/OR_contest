"""Minimal live-seafood recovery and dispatch check.

Two batches, one recovery slot, two recovery periods, a common deadline, and
different transport survival multipliers. The exact DP is compared with FIFO,
worst-state-first, and EDD. The instance is illustrative, not calibrated.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

from src.runtime import results_root

SURVIVAL = (0.5, 0.8, 0.9)
MULTIPLIER = {0: 1.0, 1: 0.6}
DEADLINE = 2
PERIODS = 3
HOLDING = 0.0


def value_at_dispatch(x_a, x_b):
    return SURVIVAL[x_a] * MULTIPLIER[0] + SURVIVAL[x_b] * MULTIPLIER[1]


def exact():
    def best(t, x_a, x_b):
        if t == DEADLINE:
            return value_at_dispatch(x_a, x_b)
        holding = -HOLDING * 2
        options = [best(t + 1, x_a, x_b)]
        if x_a < 2:
            options.append(best(t + 1, x_a + 1, x_b))
        if x_b < 2:
            options.append(best(t + 1, x_a, x_b + 1))
        return holding + max(options)

    return best(0, 0, 0)


def replay(recover):
    """Recover is a list of two actions, each 0=A, 1=B, or None=idle."""
    states = [0, 0]
    for action in recover:
        if action is not None and states[action] < 2:
            states[action] += 1
    return value_at_dispatch(states[0], states[1]), states


def fifo():
    # Batch B arrived first, so FIFO gives it the slot first.
    return replay([1, 1])


def worst_state_first():
    # Both start at the worst state; tie broken by arrival order (B first).
    return replay([1, 1])


def edd():
    # Common deadline; tie broken by arrival order (B first).
    return replay([1, 1])


def main():
    rows = [
        {"policy": "exact", "value": exact(), "states": None},
        {"policy": "fifo", "value": fifo()[0], "states": fifo()[1]},
        {"policy": "worst_state_first", "value": worst_state_first()[0], "states": worst_state_first()[1]},
        {"policy": "edd", "value": edd()[0], "states": edd()[1]},
    ]
    summary = {
        "survival": SURVIVAL,
        "multiplier": {str(key): value for key, value in MULTIPLIER.items()},
        "deadline": DEADLINE,
        "periods": PERIODS,
        "rows": rows,
        "exact_beats_all": all(row["value"] < rows[0]["value"] - 1e-9 for row in rows[1:]),
        "best_gap": rows[0]["value"] - max(row["value"] for row in rows[1:]),
        "scope": "two batches, one recovery slot, common deadline; illustrative parameters",
        "limitations": [
            "Survival probabilities are assumed, not estimated.",
            "Recovery is deterministic and cannot revive dead animals.",
            "Only one slot and two batches; no transport duration or order value heterogeneity.",
        ],
    }
    out_dir = results_root() / "live_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("exact_beats_all", "best_gap")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
