"""Recompute saved forecast errors from original dated observations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd


def verify(folder, expected_methods=None):
    if not __debug__:
        raise RuntimeError("验收必须启用断言，禁止使用 python -O")
    report = json.loads((folder / "rolling_backtest.json").read_text(encoding="utf-8"))
    raw_path = ROOT / "data/raw/df_past_order.csv"
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == report["history_sha256"]
    actual = pd.read_csv(raw_path).set_index(["Name", "SKU"])
    actual.columns = pd.to_datetime(actual.columns).strftime("%Y/%m/%d")
    dates_all = pd.to_datetime(actual.columns)
    parameters = report["parameters"]
    minimum, horizon, step = (parameters[name] for name in ("min_train", "horizon", "step"))
    assert all(isinstance(value, int) and value > 0 for value in (minimum, horizon, step))
    assert len(dates_all) >= minimum+horizon
    origins = list(range(minimum, len(dates_all)-horizon+1, step))
    if origins[-1] != len(dates_all)-horizon:
        origins.append(len(dates_all)-horizon)
    methods = set(report["summary"])
    assert methods and all(name.replace("_", "").isalnum() for name in methods)
    # Without an explicit target the method set is self-referential: it only
    # proves the report agrees with itself, so an entire method silently
    # dropped by a missing dependency would pass. The CLI requires the flag,
    # and a direct call that omits it records that completeness was not asserted.
    method_set_asserted = expected_methods is not None
    if method_set_asserted:
        assert methods == set(expected_methods), "实际方法集合不符合本次验收目标"
    pairs = [(row["window"], row["method"]) for row in report["windows"]]
    assert len(pairs) == len(set(pairs)), "重复的窗口/方法记录"
    assert set(pairs) == {(window, method) for window in range(1, len(origins)+1) for method in methods}, "缺失或多余的窗口/方法"
    assert report["target_date_events_per_series"] == len(origins)*horizon
    assert report["distinct_target_dates"] == len({date for origin in origins for date in dates_all[origin:origin+horizon]})
    errors = {}
    input_hashes = {"rolling_backtest.json": hashlib.sha256((folder/"rolling_backtest.json").read_bytes()).hexdigest()}
    for row in report["windows"]:
        origin = origins[row["window"]-1]
        assert row["train_days"] == origin
        assert pd.Timestamp(row["train_start"]) == dates_all[0]
        assert pd.Timestamp(row["train_end"]) == dates_all[origin-1]
        assert pd.Timestamp(row["validation_start"]) == dates_all[origin]
        assert pd.Timestamp(row["validation_end"]) == dates_all[origin+horizon-1]
        prediction_path = folder / f"window_{row['window']}" / f"{row['method']}.csv"
        input_hashes[prediction_path.relative_to(folder).as_posix()] = hashlib.sha256(prediction_path.read_bytes()).hexdigest()
        predicted = pd.read_csv(prediction_path)
        assert not predicted.duplicated(["Customer", "SKU"]).any()
        predicted = predicted.set_index(["Customer", "SKU"])
        assert set(predicted.index) == set(actual.index)
        predicted = predicted.reindex(actual.index)
        dates = pd.to_datetime(predicted.columns)
        expected_dates = pd.date_range(row["validation_start"], row["validation_end"])
        assert dates.equals(expected_dates)
        assert pd.Timestamp(row["train_end"]) < dates.min()
        truth = actual.loc[:, predicted.columns].to_numpy(dtype=float)
        values = predicted.to_numpy(dtype=float)
        assert np.isfinite(values).all() and (values >= 0).all()
        sse = float(np.square(values-truth).sum())
        assert np.isclose(np.sqrt(sse/truth.size), row["metrics"]["rmse"], rtol=1e-12)
        assert truth.size == row["points"]
        if row["method"] == "SeasonalNaive":
            assert origin >= 7
            past_columns = [dates_all[origin-7+index % 7].strftime("%Y/%m/%d") for index in range(horizon)]
            np.testing.assert_allclose(values, actual.loc[:, past_columns].to_numpy())
        errors.setdefault(row["method"], []).append((sse, truth.size))
    for method, rows in errors.items():
        rmse = np.sqrt(sum(row[0] for row in rows)/sum(row[1] for row in rows))
        assert np.isclose(rmse, report["summary"][method]["forecast_event_rmse"], rtol=1e-12)
        assert sum(row[1] for row in rows) == report["summary"][method]["forecast_events"]
        selected = [row for row in report["windows"] if row["method"] == method]
        summary = report["summary"][method]
        assert np.isclose(np.mean([row["metrics"]["rmse"] for row in selected]), summary["mean_window_rmse"], rtol=1e-12)
        assert min(row["rank"] for row in selected) == summary["best_rank"]
        assert max(row["rank"] for row in selected) == summary["worst_rank"]
        assert sum(row["rank"] == 1 for row in selected) == summary["windows_tied_for_best"]
    for row in report["windows"]:
        peers = [other for other in report["windows"] if other["window"] == row["window"]]
        rank = 1+sum(other["metrics"]["rmse"] < row["metrics"]["rmse"]-1e-12 for other in peers)
        assert row["rank"] == rank, "窗口排名与已重算误差不一致"
    return {"prediction_files_checked": len(report["windows"]), "methods": len(errors),
            "method_set_asserted": method_set_asserted,
            "checks": "complete method/window grid, input hash, keys, exact training/validation dates, overlap counts, predictions, independent RMSE, event counts, ranks and weekly baseline",
            "history_sha256": report["history_sha256"], "inputs_sha256": input_hashes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-methods", required=True,
                        help="本次验收必须包含的方法，逗号分隔；不允许静默跳过")
    args = parser.parse_args()
    expected = [name for name in args.expected_methods.split(",") if name]
    if not expected:
        parser.error("--expected-methods 不能为空；否则无法断言方法集合完整")
    result = verify(args.folder, expected)
    result.update(checked_at_utc=datetime.now(timezone.utc).isoformat(), command=[sys.executable, *sys.argv],
                  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
