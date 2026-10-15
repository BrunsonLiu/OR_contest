"""Forecasts with a chronological holdout and explicit prediction provenance."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor

from src.runtime import ROOT, results_root

HORIZON = 7
FUTURE_DATES = pd.date_range("2016-06-24", "2016-06-30")
CITY_COLUMNS = ["Longitude", "Latitude", "city_area", "builtup_area", "resident_pop", "gdp"]


def time_features(dates):
    dates = pd.DatetimeIndex(dates)
    return pd.DataFrame({
        "time_idx": (dates - pd.Timestamp("2016-06-01")).days,
        "weekday": dates.dayofweek,
        "weekend": (dates.dayofweek >= 5).astype(int),
        "sin_week": np.sin(2 * np.pi * dates.dayofweek / 7),
        "cos_week": np.cos(2 * np.pi * dates.dayofweek / 7),
    })


def load_history():
    frame = pd.read_csv(ROOT / "data/raw/df_past_order.csv")
    dates = pd.to_datetime(frame.columns[2:], format="%Y/%m/%d")
    if not dates.is_unique or not dates.is_monotonic_increasing or len(dates) <= HORIZON:
        raise ValueError("历史日期必须唯一、递增，并且多于一个预测周期")
    if dates[-1] + pd.Timedelta(days=1) != FUTURE_DATES[0]:
        raise ValueError("历史订单必须截止到预测开始日的前一天")
    if not dates.equals(pd.date_range(dates[0], dates[-1])):
        raise ValueError("历史订单日期存在缺口")
    values = frame.iloc[:, 2:].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any() or frame.duplicated(["Name", "SKU"]).any():
        raise ValueError("历史订单存在非有限值、负需求或重复门店/SKU")
    return frame, dates, values


def make_model(method, sku):
    if method == "GradientBoosting":
        return GradientBoostingRegressor(n_estimators=100 if sku == "dm" else 150,
                                         max_depth=5 if sku == "dm" else 7,
                                         learning_rate=0.05 if sku == "dm" else 0.1, random_state=42)
    if method == "RandomForest":
        return RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42, n_jobs=1)
    if method == "SVR":
        return make_pipeline(StandardScaler(), SVR())
    if method == "MLP":
        return make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(50,), max_iter=500, random_state=42))
    if method == "LightGBM":
        from lightgbm import LGBMRegressor
        return LGBMRegressor(n_estimators=100, max_depth=5, random_state=42, n_jobs=1, verbosity=-1)
    raise ValueError(f"未知方法：{method}")


def predict_series(values, history_dates, target_dates, sku, method="GradientBoosting"):
    model = make_model(method, sku)
    model.fit(time_features(history_dates), np.asarray(values, dtype=float))
    return np.maximum(model.predict(time_features(target_dates)), 0)


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    error = predicted - actual
    nonzero = actual != 0
    return {
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "mean_series_rmse": float(np.mean(np.sqrt(np.mean(error ** 2, axis=1)))),
        "mae": float(np.mean(np.abs(error))),
        "mape_percent_nonzero": float(np.mean(np.abs(error[nonzero] / actual[nonzero])) * 100) if nonzero.any() else None,
        "mape_excluded_zero_points": int((~nonzero).sum()),
    }


def write_predictions(folder, filename, history, values, dates):
    result = pd.DataFrame(values, columns=[date.strftime("%Y/%m/%d") for date in dates])
    result.insert(0, "SKU", history["SKU"].to_numpy())
    result.insert(0, "Customer", history["Name"].to_numpy())
    result.to_csv(folder / filename, index=False, encoding="utf-8-sig")
    return result


def evaluate_and_save(name, filename, predictor, frame, dates, values, folder):
    # Fit independent models on June 1–16, predict June 17–23. The holdout is never passed to fitting.
    keys = frame.loc[:, ["Name", "SKU"]].copy()
    validation = predictor(keys, values[:, :-HORIZON].copy(), dates[:-HORIZON], dates[-HORIZON:])
    future = predictor(keys, values.copy(), dates, FUTURE_DATES)
    for array in (validation, future):
        if array.shape != (len(frame), HORIZON) or not np.isfinite(array).all() or (array < 0).any():
            raise ValueError(f"{name} 生成的预测不符合输出契约")
    write_predictions(folder, filename, frame, future, FUTURE_DATES)
    write_predictions(folder, f"validation_{name}.csv", frame, validation, dates[-HORIZON:])
    result = {
        "method": name,
        "validation": metrics(values[:, -HORIZON:], validation),
        "validation_by_sku": {sku: metrics(values[frame["SKU"].eq(sku), -HORIZON:], validation[frame["SKU"].eq(sku)])
                              for sku in sorted(frame["SKU"].unique())},
        "seasonal_naive_validation": metrics(values[:, -HORIZON:], values[:, -2*HORIZON:-HORIZON]),
        "validation_train_end": str(dates[-HORIZON-1].date()),
        "validation_dates": [str(d.date()) for d in dates[-HORIZON:]],
        "forecast_train_end": str(dates[-1].date()),
        "forecast_dates": [str(d.date()) for d in FUTURE_DATES],
        "history_sha256": hashlib.sha256((ROOT / "data/raw/df_past_order.csv").read_bytes()).hexdigest(),
        "random_state": 42,
        "hyperparameter_search": False,
        "future_accuracy": "unknown: no actual observations for the forecast week are provided",
    }
    (folder / f"metrics_{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"{name}: holdout RMSE={result['validation']['rmse']:.4f}; seasonal naive RMSE={result['seasonal_naive_validation']['rmse']:.4f}")
    return result


def per_series(method):
    def predict(frame, values, dates, target_dates):
        return np.vstack([predict_series(values[i], dates, target_dates, row.SKU, method)
                          for i, row in enumerate(frame.itertuples(index=False))])
    return predict


def city_predictor(include_city):
    locations = pd.read_csv(ROOT / "data/raw/df_customer.csv").set_index("Name")["Location"]
    cities = pd.read_csv(ROOT / "data/raw/df_loc.csv").set_index("Location")

    def design(frame, dates):
        blocks = []
        for row in frame.itertuples(index=False):
            block = time_features(dates)
            if include_city:
                # Use the exact customer/location mapping; do not guess from name prefixes.
                city = cities.loc[locations.loc[row.Name], CITY_COLUMNS].astype(float)
                if city.isna().any():
                    raise ValueError(f"城市特征缺失：{row.Name}")
                for key in CITY_COLUMNS:
                    block[key] = city[key]
            blocks.append(block)
        return pd.concat(blocks, ignore_index=True)

    def predict(frame, values, dates, target_dates):
        output = np.zeros((len(frame), len(target_dates)))
        for sku in sorted(frame["SKU"].unique()):
            mask = frame["SKU"].eq(sku).to_numpy()
            subset = frame.loc[mask]
            model = make_model("GradientBoosting", sku)
            model.fit(design(subset, dates), values[mask].reshape(-1))
            output[mask] = np.maximum(model.predict(design(subset, target_dates)), 0).reshape(-1, len(target_dates))
        return output
    return predict


def run_forecasts(mode="baseline"):
    frame, dates, values = load_history()
    folder = results_root() / "question3"
    folder.mkdir(parents=True, exist_ok=True)
    if mode == "baseline":
        tasks = [("GradientBoosting", "订单需求量预测结果文件.csv", per_series("GradientBoosting"))]
    elif mode == "city":
        tasks = [("pooled_time", "订单需求量预测结果_实验一_纯时间序列.csv", city_predictor(False)),
                 ("pooled_city", "订单需求量预测结果_实验二_加入城市特征.csv", city_predictor(True))]
    elif mode == "methods":
        methods = ["RandomForest", "GradientBoosting", "SVR", "MLP"]
        try:
            import lightgbm  # noqa: F401
        except ImportError:
            pass
        else:
            methods.append("LightGBM")
        tasks = [(name, f"预测结果_{name}.csv", per_series(name)) for name in methods]
    else:
        raise ValueError(mode)
    reports = [evaluate_and_save(name, filename, predictor, frame, dates, values, folder)
               for name, filename, predictor in tasks]
    (folder / f"comparison_{mode}.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    return reports
