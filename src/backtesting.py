"""Expanding-window forecasting comparisons with explicit overlap accounting."""
import hashlib
import json
import time

import numpy as np

from src.forecasting import ROOT, city_predictor, load_history, metrics, per_series, write_predictions
from src.runtime import results_root


def rolling_splits(n_days, min_train=7, horizon=7, step=3):
    if min(min_train, horizon, step) < 1 or n_days < min_train+horizon:
        raise ValueError("历史长度不足，或窗口参数不是正数")
    origins = list(range(min_train, n_days-horizon+1, step))
    if origins[-1] != n_days-horizon:
        origins.append(n_days-horizon)
    return [(origin, origin+horizon) for origin in origins]


def seasonal_naive(keys, values, dates, target_dates):
    if values.shape[1] < 7:
        raise ValueError("同星期基线至少需要 7 天历史")
    return values[:, values.shape[1]-7 + np.arange(len(target_dates)) % 7].copy()


def last_value(keys, values, dates, target_dates):
    return np.repeat(values[:, -1:], len(target_dates), axis=1)


def evaluate_windows(frame, dates, values, factories, splits, sink=None):
    if not factories or not splits:
        raise ValueError("回测方法与窗口不能为空")
    keys = frame.loc[:, ["Name", "SKU"]].copy()
    rows = []
    for window, (origin, end) in enumerate(splits, 1):
        if not 0 < origin < end <= len(dates):
            raise ValueError("非法回测窗口")
        targets = dates[origin:end]
        for name, factory in factories.items():
            predictor = factory()  # No fitted estimator state is shared between origins.
            start = time.monotonic()
            predicted = np.asarray(predictor(keys.copy(), values[:, :origin].copy(), dates[:origin], targets), dtype=float)
            if predicted.shape != (len(keys), end-origin) or not np.isfinite(predicted).all() or (predicted < 0).any():
                raise ValueError(f"{name} 输出不符合回测契约")
            actual = values[:, origin:end]
            row = {"window": window, "method": name, "train_days": origin,
                   "train_start": str(dates[0].date()), "train_end": str(dates[origin-1].date()),
                   "validation_start": str(targets[0].date()), "validation_end": str(targets[-1].date()),
                   "points": int(actual.size), "metrics": metrics(actual, predicted),
                   "by_sku": {sku: metrics(actual[keys.SKU.eq(sku)], predicted[keys.SKU.eq(sku)])
                              for sku in sorted(keys.SKU.unique())},
                   "elapsed_seconds": round(time.monotonic()-start, 3)}
            rows.append(row)
            if sink:
                sink(row, predicted, targets)
            print(f"window={window} train={origin} method={name}: RMSE={row['metrics']['rmse']:.4f}", flush=True)
        window_rows = [row for row in rows if row["window"] == window]
        for row in window_rows:
            row["rank"] = 1+sum(other["metrics"]["rmse"] < row["metrics"]["rmse"]-1e-12 for other in window_rows)
    summary = {}
    for name in factories:
        selected = [row for row in rows if row["method"] == name]
        count = sum(row["points"] for row in selected)
        summary[name] = {
            "mean_window_rmse": float(np.mean([row["metrics"]["rmse"] for row in selected])),
            "forecast_event_rmse": float(np.sqrt(sum(row["points"]*row["metrics"]["rmse"]**2 for row in selected)/count)),
            "best_rank": min(row["rank"] for row in selected), "worst_rank": max(row["rank"] for row in selected),
            "windows_tied_for_best": sum(row["rank"] == 1 for row in selected), "forecast_events": count,
        }
    return {"windows": rows, "summary": summary,
            "target_date_events_per_series": sum(end-origin for origin, end in splits),
            "distinct_target_dates": len({str(date.date()) for origin, end in splits for date in dates[origin:end]}),
            "overlap_caveat": "Overlapping windows are not independent replicates; no significance or population ranking claim is made."}


def run_backtest():
    frame, dates, values = load_history()
    factories = {"SeasonalNaive": lambda: seasonal_naive, "LastValue": lambda: last_value,
                 "pooled_time": lambda: city_predictor(False), "pooled_city": lambda: city_predictor(True)}
    for method in ("RandomForest", "GradientBoosting", "SVR", "MLP", "LightGBM"):
        if method == "LightGBM":
            try:
                import lightgbm  # noqa: F401
            except ImportError:
                continue
        factories[method] = lambda method=method: per_series(method)
    folder = results_root() / "question3/backtests"
    folder.mkdir(parents=True, exist_ok=True)

    def save(row, predicted, targets):
        window = folder / f"window_{row['window']}"
        window.mkdir(exist_ok=True)
        write_predictions(window, f"{row['method']}.csv", frame, predicted, targets)

    splits = rolling_splits(len(dates))
    report = evaluate_windows(frame, dates, values, factories, splits, save)
    report.update(history_sha256=hashlib.sha256((ROOT / "data/raw/df_past_order.csv").read_bytes()).hexdigest(),
                  parameters={"min_train": 7, "horizon": 7, "step": 3, "random_state": 42,
                              "parameter_search": False, "method_selection": "fixed before this rolling evaluation"})
    (folder / "rolling_backtest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    import pandas as pd
    pd.DataFrame([{key: value for key, value in row.items() if key not in ("metrics", "by_sku")}
                  | row["metrics"] for row in report["windows"]]).to_csv(folder / "window_scores.csv", index=False, encoding="utf-8-sig")
    print(f"Backtest report saved to {folder}")
    return report
