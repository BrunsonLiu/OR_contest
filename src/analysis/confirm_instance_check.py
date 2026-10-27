"""Exact dynamic program for the confirmation-instance mechanism check.

One picker, one order, three nodes on a line: depot, stockout shelf A,
substitute shelf A', and one other item B. The picker may keep working while
a confirmation reply is pending. A reply makes A' executable only if it
arrives by the order's confirmation window; checking out closes that window.
The program compares the full mechanism with two frozen variants:

* frozen task set: A' is treated as pre-approved at time zero;
* frozen window: the reply may be used until the delivery deadline.

This is a mechanism check on small instances, not a policy for a real store.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json
from functools import lru_cache
from pathlib import Path

from src.runtime import results_root

PICK_SUB = 1
PICK_OTHER = 2


def _normalise(t, pos, avail, reply_delay, window, deadline):
    """A request is sent on first arrival at the stockout shelf; earlier is weakly better."""
    if pos == 1 and avail == -1:
        arrival = t + reply_delay
        return arrival if arrival <= window else deadline + 1
    return avail


def solve_instance(other_position, reply_delay, window, deadline,
                   value_substitute=1.0, value_other=1.0, preapproved=False):
    """Return the optimal delivered value, finish time and an action sequence.

    Nodes: 0 depot, 1 stockout A, 2 substitute A', other_position = B.
    Travel is along adjacent nodes at unit speed; picking takes no time.
    """
    if not (other_position >= 3 and deadline >= 0 and window >= 0 and reply_delay >= 0):
        raise ValueError("实例参数必须满足 other_position>=3，时间参数非负")
    edges = {(0, 1): 1.0, (1, 0): 1.0, (1, 2): 1.0, (2, 1): 1.0,
             (2, other_position): float(other_position - 2), (other_position, 2): float(other_position - 2)}
    neighbours = {0: (1,), 1: (0, 2), 2: (1, other_position), other_position: (2,)}

    def delivered(mask):
        return (value_substitute if mask & PICK_SUB else 0.0) + (value_other if mask & PICK_OTHER else 0.0)

    choice = {}

    @lru_cache(maxsize=None)
    def best(t, pos, mask, avail):
        avail = _normalise(t, pos, avail, reply_delay, window, deadline)
        options = [("stop", 1000.0 * delivered(mask) - t)]
        if t < deadline:
            options.append(("wait", best(t + 1, pos, mask, avail)))
        for nxt in neighbours[pos]:
            t2 = t + edges[(pos, nxt)]
            if t2 <= deadline:
                options.append((("move", nxt), best(t2, nxt, mask, avail)))
        if pos == 2 and not (mask & PICK_SUB) and avail <= t:
            options.append((("pick", "sub"), best(t, pos, mask | PICK_SUB, avail)))
        if pos == other_position and not (mask & PICK_OTHER):
            options.append((("pick", "other"), best(t, pos, mask | PICK_OTHER, avail)))
        action, score = max(options, key=lambda item: item[1])
        choice[(t, pos, mask, avail)] = action
        return score

    start_avail = 0 if preapproved else -1
    score = best(0, 0, 0, start_avail)

    # Reconstruct the optimal plan from the memoised choices.
    t, pos, mask, avail = 0, 0, 0, start_avail
    plan = []
    while True:
        avail = _normalise(t, pos, avail, reply_delay, window, deadline)
        action = choice[(t, pos, mask, avail)]
        plan.append({"time": t, "position": pos, "action": action, "available_substitute": avail})
        if action == "stop":
            break
        if action == "wait":
            t += 1
        elif action[0] == "move":
            t += edges[(pos, action[1])]
            pos = action[1]
        elif action == ("pick", "sub"):
            mask |= PICK_SUB
        elif action == ("pick", "other"):
            mask |= PICK_OTHER
    return {"value": delivered(mask), "finish": t, "plan": plan,
            "picked_substitute_at": next((step["time"] for step in plan if step["action"] == ("pick", "sub")), None)}


def realised_frozen_plan(plan, other_position, reply_delay, window, deadline,
                         value_substitute=1.0, value_other=1.0):
    """Replay the pre-approved plan under the full confirmation rules."""
    edges = {(0, 1): 1.0, (1, 0): 1.0, (1, 2): 1.0, (2, 1): 1.0,
             (2, other_position): float(other_position - 2), (other_position, 2): float(other_position - 2)}
    t, pos, mask, avail = 0, 0, 0, -1
    violation = False
    for step in plan:
        avail = _normalise(t, pos, avail, reply_delay, window, deadline)
        action = step["action"]
        if action == "stop":
            break
        if action == "wait":
            t += 1
        elif action[0] == "move":
            t += edges[(pos, action[1])]
            pos = action[1]
        elif action == ("pick", "sub"):
            if avail <= t:
                mask |= PICK_SUB
            else:
                violation = True
        elif action == ("pick", "other"):
            mask |= PICK_OTHER
    value = (value_substitute if mask & PICK_SUB else 0.0) + (value_other if mask & PICK_OTHER else 0.0)
    return {"value": value, "violation": violation, "finish": t}


def build_grid():
    rows = []
    for other_position in (8.0, 10.0, 12.0):
        for reply_delay in (1, 2, 3, 4, 5, 6, 8):
            for deadline in (10, 12, 14):
                for window in sorted({deadline, max(deadline - 2, 1), max(deadline - 4, 1), max(deadline - 6, 1)}):
                    for values in ((1.0, 1.0), (2.0, 1.0)):
                        rows.append({"other_position": other_position, "reply_delay": reply_delay,
                                     "deadline": deadline, "window": window,
                                     "value_substitute": values[0], "value_other": values[1]})
    return rows


def evaluate(instance):
    common = dict(other_position=instance["other_position"], reply_delay=instance["reply_delay"],
                  window=instance["window"], deadline=instance["deadline"],
                  value_substitute=instance["value_substitute"], value_other=instance["value_other"])
    full = solve_instance(**common)
    frozen = solve_instance(**common, preapproved=True)
    frozen_real = realised_frozen_plan(frozen["plan"], other_position=instance["other_position"],
                                       reply_delay=instance["reply_delay"], window=instance["window"],
                                       deadline=instance["deadline"],
                                       value_substitute=instance["value_substitute"],
                                       value_other=instance["value_other"])
    no_window = solve_instance(**{**common, "window": instance["deadline"]})
    return {**instance,
            "full_value": full["value"], "full_finish": full["finish"],
            "frozen_value": frozen["value"], "frozen_realised": frozen_real["value"],
            "frozen_violation": frozen_real["violation"],
            "window_value": no_window["value"],
            "gap_vs_frozen": full["value"] - frozen_real["value"],
            "gap_vs_window": full["value"] - no_window["value"]}


def summarise(rows):
    def count(predicate):
        return sum(1 for row in rows if predicate(row))
    return {
        "instances": len(rows),
        "frozen_plan_loses_value": count(lambda r: r["gap_vs_frozen"] > 0),
        "frozen_plan_violates_window": count(lambda r: r["frozen_violation"]),
        "window_binds": count(lambda r: r["gap_vs_window"] < 0),
        "full_differs_from_frozen_or_window": count(lambda r: r["gap_vs_frozen"] > 0 or r["gap_vs_window"] < 0),
        "max_value_loss_vs_frozen": max((r["gap_vs_frozen"] for r in rows), default=0.0),
        "max_value_loss_vs_window": max((-r["gap_vs_window"] for r in rows), default=0.0),
        "by_reply_delay": {
            str(delay): count(lambda r, d=delay: r["reply_delay"] == d and
                              (r["gap_vs_frozen"] > 0 or r["gap_vs_window"] < 0))
            for delay in sorted({r["reply_delay"] for r in rows})},
        "by_window_slack": {
            str(slack): count(lambda r, s=slack: r["deadline"] - r["window"] == s and
                              (r["gap_vs_frozen"] > 0 or r["gap_vs_window"] < 0))
            for slack in sorted({r["deadline"] - r["window"] for r in rows})},
        "scope": "small exact DP instances; no real store data, no algorithm comparison",
        "limitations": [
            "Deterministic reply delay and approve-all replies; no rejection branch.",
            "One stockout and one substitute; no batching of requests or multi-order picking.",
            "The frozen plan is replayed under full rules; its value is an observed violation, not a deployable policy.",
        ],
    }


def main():
    rows = [evaluate(instance) for instance in build_grid()]
    out_dir = results_root() / "confirm_instance"
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["other_position", "reply_delay", "deadline", "window", "value_substitute", "value_other",
              "full_value", "full_finish", "frozen_value", "frozen_realised", "frozen_violation",
              "window_value", "gap_vs_frozen", "gap_vs_window"]
    with (out_dir / "instances.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarise(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("instances", "frozen_plan_loses_value", "frozen_plan_violates_window",
                       "window_binds", "full_differs_from_frozen_or_window")}, ensure_ascii=False))
    print("Small exact DP; no algorithm claim. Outputs:", out_dir)


if __name__ == "__main__":
    main()
