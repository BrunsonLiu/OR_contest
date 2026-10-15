"""Reconstruct the historical forecast to establish provenance, not accuracy."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder

LEGACY_REF = "bf0f2065b2cc150cca548d9c841a8735e79b4bb4:src/solvers/question3/solve_problem3.py"


def verify(output_dir):
    code = subprocess.check_output(["git", "show", LEGACY_REF], cwd=ROOT, text=True, encoding="utf-8")
    tree = ast.parse(code)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in
                 ("normalize_features", "create_features_for_ts", "advanced_forecast")]
    if len(functions) != 3:
        raise RuntimeError("历史预测函数缺失")
    namespace = {"pd": pd, "np": np, "GradientBoostingRegressor": GradientBoostingRegressor}
    # Only the three functions are loaded; historical top-level file writes are never run.
    exec(compile(ast.Module(body=functions, type_ignores=[]), LEGACY_REF, "exec"), namespace)
    history_path = ROOT / "data/raw/df_past_order.csv"
    forecast_path = ROOT / "results/question3/订单需求量预测结果文件_sota.csv"
    history = pd.read_csv(history_path)
    saved = pd.read_csv(forecast_path).set_index(["Customer", "SKU"])
    dates = pd.to_datetime(history.columns[2:], format="%Y/%m/%d")
    future_dates = pd.date_range("2016-06-24", "2016-06-30")
    city_names = history.Name.apply(lambda name: name.rsplit("-", 1)[0])
    encoder = LabelEncoder().fit(city_names)
    rebuilt, reference = [], []
    for _, row in history.iterrows():
        city = encoder.transform([row.Name.rsplit("-", 1)[0]])[0]
        rebuilt.append(namespace["advanced_forecast"](row.iloc[2:].to_numpy(float), dates, future_dates, row.SKU, city))
        reference.append(saved.loc[(row.Name, row.SKU)].to_numpy(float))
    rebuilt, reference = np.asarray(rebuilt), np.asarray(reference)
    report = {
        "source_git_ref": LEGACY_REF,
        "historical_source_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "history_sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
        "forecast_sha256": hashlib.sha256(forecast_path.read_bytes()).hexdigest(),
        "series": len(history), "points": int(rebuilt.size),
        "max_absolute_difference": float(np.max(np.abs(rebuilt-reference))),
        "all_points_match_atol_1e-9": bool(np.allclose(rebuilt, reference, atol=1e-9, rtol=0)),
        "caveat": "Numerical reconstruction does not validate historical accuracy. Legacy evaluation compares different weeks and is invalid.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "legacy_forecast_provenance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    result = pd.DataFrame(rebuilt, columns=saved.columns)
    result.insert(0, "SKU", history.SKU.to_numpy())
    result.insert(0, "Customer", history.Name.to_numpy())
    result.to_csv(output_dir / "legacy_forecast_reconstructed.csv", index=False, encoding="utf-8-sig")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_points_match_atol_1e-9"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(verify(args.output_dir.resolve()))
