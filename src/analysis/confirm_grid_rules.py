"""Timing, order and stop-before-substitute rules for the 2D instance.

The family covers: skip or visit the stockout; wait k minutes after the
request; serve other items nearest-first or farthest-first; take the
substitute before or after the other items; and stop after at most m other
items before trying the substitute. The best member is compared with the exact
DP on the same instances, so the rule family is deliberately strong.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json

from src.analysis.confirm_grid2d import (A, NODES, OTHERS, S, VALUES, distance,
                                         solve_exact)
from src.runtime import results_root

WAITS = (0, 1, 2, 3, 4)
ORDERS = ("nearest", "farthest")
S_FIRST = (False, True)
MAX_BEFORE = (0, 1, 2, 3)


def _pick_order(t, pos, remaining, order, deadline, limit=None):
    value = 0.0
    served = 0
    while remaining and (limit is None or served < limit):
        if order == "nearest":
            target = min(remaining, key=lambda node: distance(pos, node))
        else:
            target = max(remaining, key=lambda node: distance(pos, node))
        arrival = t + distance(pos, target)
        if arrival > deadline:
            break
        t, pos = arrival, target
        value += VALUES[target]
        served += 1
        remaining = [node for node in remaining if node != target]
    return t, pos, value, remaining


def _scenarios(dist, reject_probability):
    for delay, probability in dist.items():
        for approved in (True, False):
            yield delay, approved, probability * ((1.0 - reject_probability) if approved else reject_probability)


def policy_value(dist, reject_probability, window, deadline, visit, wait_k, order, s_first, max_before):
    if not visit:
        _, _, value, _ = _pick_order(0, 0, list(OTHERS), order, deadline)
        return value

    total = 0.0
    for delay, approved, probability in _scenarios(dist, reject_probability):
        t, pos, value = distance(0, A), A, 0.0
        request = t
        reply = request + delay
        usable = reply <= window and approved
        picked_sub = False
        remaining = list(OTHERS)
        if usable and delay <= wait_k and s_first:
            arrival = reply + distance(A, S)
            if arrival <= deadline:
                t, pos = arrival, S
                value += VALUES[S]
                picked_sub = True
        if t < request + wait_k:
            t = request + wait_k
        if not picked_sub:
            t, pos, others, remaining = _pick_order(t, pos, remaining, order, deadline,
                                                    limit=None if not usable else max_before)
            value += others
        if usable and not picked_sub:
            arrival = t + distance(pos, S)
            finish = max(arrival, reply)
            if finish <= deadline:
                t, pos = finish, S
                value += VALUES[S]
                picked_sub = True
        if remaining and picked_sub:
            _, _, others, remaining = _pick_order(t, pos, remaining, order, deadline)
            value += others
        elif remaining:
            _, _, others, remaining = _pick_order(t, pos, remaining, order, deadline)
            value += others
        total += probability * value
    return total


def family_values(dist, reject_probability, window, deadline):
    values = {}
    for visit in (False, True):
        for wait_k in WAITS:
            for order in ORDERS:
                for s_first in S_FIRST:
                    for max_before in MAX_BEFORE:
                        key = (visit, wait_k, order, s_first, max_before)
                        values[key] = policy_value(dist, reject_probability, window, deadline,
                                                   visit, wait_k, order, s_first, max_before)
    return values


def grid():
    dist = {2: 0.2, 3: 0.3, 4: 0.3, 5: 0.2}
    return [{"deadline": deadline, "window": window, "reject_probability": reject, "dist": dist}
            for deadline in (6, 7, 8, 10)
            for window in (deadline, deadline - 2)
            for reject in (0.0, 0.2)]


def evaluate(row):
    full = solve_exact(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    family = family_values(row["dist"], row["reject_probability"], row["window"], row["deadline"])
    best_key, best_value = max(family.items(), key=lambda item: item[1])
    return {"deadline": row["deadline"], "window": row["window"],
            "reject_probability": row["reject_probability"], "full_value": full,
            "best_rule_value": best_value, "gap": full - best_value,
            "best_visit": best_key[0], "best_wait": best_key[1], "best_order": best_key[2],
            "best_s_first": best_key[3], "best_max_before": best_key[4]}


def main():
    rows = [evaluate(row) for row in grid()]
    out_dir = results_root() / "confirm_grid_rules"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["deadline", "window", "reject_probability", "full_value", "best_rule_value",
              "gap", "best_visit", "best_wait", "best_order", "best_s_first", "best_max_before"]
    with (out_dir / "rules.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "instances": len(rows),
        "full_beats_best_rule": sum(1 for row in rows if row["gap"] > 1e-9),
        "max_gap": max(row["gap"] for row in rows),
        "by_reject_probability": {
            str(q): {
                "instances": sum(1 for row in rows if row["reject_probability"] == q),
                "beats": sum(1 for row in rows if row["reject_probability"] == q and row["gap"] > 1e-9),
            } for q in sorted({row["reject_probability"] for row in rows})},
        "scope": "timing, order and stop-before-substitute family versus exact DP on a 4x4 grid",
        "limitations": [
            "The family is chosen per instance, which favours the baseline.",
            "One stockout, three other items; no real store data.",
            "The family is finite; a different rule could still close the remaining gap.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("instances", "full_beats_best_rule", "max_gap")},
                     ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
