"""Recompute saved forecast errors from original dated observations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd


def verify(folder):
    report = json.loads((folder / "rolling_backtest.json").read_text(encoding="utf-8"))
    raw_path = ROOT / "data/raw/df_past_order.csv"
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == report["history_sha256"]
    actual = pd.read_csv(raw_path).set_index(["Name", "SKU"])
    actual.columns = pd.to_datetime(actual.columns).strftime("%Y/%m/%d")
    errors = {}
    for row in report["windows"]:
        predicted = pd.read_csv(folder / f"window_{row['window']}" / f"{row['method']}.csv")
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
            past_columns = [(date-pd.Timedelta(days=7)).strftime("%Y/%m/%d") for date in dates]
            np.testing.assert_allclose(values, actual.loc[:, past_columns].to_numpy())
        errors.setdefault(row["method"], []).append((sse, truth.size))
    for method, rows in errors.items():
        rmse = np.sqrt(sum(row[0] for row in rows)/sum(row[1] for row in rows))
        assert np.isclose(rmse, report["summary"][method]["forecast_event_rmse"], rtol=1e-12)
    return {"prediction_files_checked": len(report["windows"]), "methods": len(errors),
            "checks": "input hash, complete keys, dates, chronology, nonnegative predictions, independent RMSE and weekly baseline"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.folder)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
