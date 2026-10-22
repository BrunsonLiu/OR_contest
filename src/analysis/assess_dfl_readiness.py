"""Inventory temporal decision cases; this does not train or validate DFL."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

import pandas as pd

from src.forecasting import FUTURE_DATES, load_history
from src.runtime import results_root


def window_inventory(dates, horizon=7, min_history=7, holdout_days=7):
    """Split label intervals, never letting training targets cross the holdout.

    Nonoverlapping target intervals are a calendar count, not a claim that
    adjacent network decisions or the cities within them are independent.
    """
    dates = pd.DatetimeIndex(dates)
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1
           for value in (horizon, min_history, holdout_days)):
        raise ValueError("窗口长度必须是正整数")
    if (dates.hasnans or not dates.is_unique or len(dates) < min_history + holdout_days
            or not dates.equals(pd.date_range(dates[0], periods=len(dates)))):
        raise ValueError("日期必须连续递增且有足够的历史和留出天数")
    boundary = len(dates) - holdout_days
    windows = []
    next_nonoverlap = 0
    nonoverlapping_pre_holdout = 0
    for origin in range(min_history, len(dates) - horizon + 1):
        end = origin + horizon
        role = ("pre_holdout" if end <= boundary else
                "within_holdout" if origin >= boundary else "crosses_holdout")
        if role == "pre_holdout" and origin >= next_nonoverlap:
            nonoverlapping_pre_holdout += 1
            next_nonoverlap = end
        windows.append({
            "history_end": str(dates[origin - 1].date()),
            "target_start": str(dates[origin].date()),
            "target_end": str(dates[end - 1].date()),
            "role": role,
        })
    counts = {role: sum(w["role"] == role for w in windows)
              for role in ("pre_holdout", "crosses_holdout", "within_holdout")}
    return {
        "horizon_days": horizon, "minimum_history_days": min_history,
        "holdout_start": str(dates[boundary].date()),
        "holdout_end": str(dates[-1].date()),
        "case_counts": counts,
        "maximum_nonoverlapping_pre_holdout_target_blocks": nonoverlapping_pre_holdout,
        "validation_reserved_within_pre_holdout": False,
        "windows": windows,
    }


def main():
    frame, dates, values = load_history()
    report = {
        "schema_version": 1,
        "scope": "calendar and raw-data inventory only; no DFL training or decision-quality comparison",
        "history": {
            "start": str(dates[0].date()), "end": str(dates[-1].date()),
            "network_days": len(dates), "city_sku_series": len(frame),
            "cities": int(frame["Name"].nunique()),
            "skus": sorted(frame["SKU"].unique().tolist()),
            "scalar_demand_observations": int(values.size),
            "weekday_observation_counts": {str(day): int((dates.dayofweek == day).sum())
                                           for day in range(7)},
            "future_week_actual_dates_in_history": len(dates.intersection(FUTURE_DATES)),
        },
        "weekly_decision_cases": window_inventory(dates),
        "daily_decision_cases": window_inventory(dates, horizon=1),
        "limitations": [
            "City/SKU rows share the same capacitated network; scalar observations are not independent network cases.",
            "Disjoint label blocks are not proof of statistical independence; histories can overlap.",
            "June 17-23 has already been used by existing forecast backtests; it is not an untouched confirmatory test.",
            "Three overlapping weekly pre-holdout cases do not yet reserve a separate validation week.",
            "This inventory does not establish the existence or absence of a DFL performance gain.",
        ],
        "not_measured": ["realized decision cost", "capacity/service violations", "regret", "DFL training cost"],
    }
    output = results_root() / "analysis" / "dfl_readiness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["history"], ensure_ascii=False))
    for key in ("weekly_decision_cases", "daily_decision_cases"):
        print(key, report[key]["case_counts"])
    print("Calendar inventory only: DFL adoption remains conditional on decision evaluation and validation evidence.")


if __name__ == "__main__":
    main()
