"""Compare last-leg and cumulative-route service definitions without changing a model."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from src.runtime import read_forecast
from src.timeliness import worst_service_ratio


def audit(path):
    records = json.loads(path.read_text(encoding="utf-8"))
    matrix = pd.read_csv(ROOT / "data/raw/df_matrix.csv").set_index(["From", "To"])
    facilities = pd.read_csv(ROOT / "data/raw/df_wh.csv")
    rdcs = facilities.loc[facilities.Type.eq("RDC"), "Name"].tolist()
    cdc = {"dm": "nei-lu-CDC", "im": "gang-kou-CDC"}
    forecast = read_forecast().set_index(["Customer", "SKU"])

    def arc(origin, destination):
        key = (origin, destination) if (origin, destination) in matrix.index else (destination, origin)
        return matrix.loc[key] if key in matrix.index else None

    policy_results = []
    for record in records:
        if "assignment_policy" not in record:
            continue
        policy = pd.DataFrame(record["assignment_policy"])
        for day, group in policy.groupby("day", sort=True):
            last_times, chain_times = [], []
            for row in group.itertuples(index=False):
                last = float(arc(row.warehouse, row.customer).Duration)
                transfer = 0 if row.warehouse == cdc[row.sku] else float(arc(cdc[row.sku], row.warehouse).Duration)
                last_times.append(last)
                chain_times.append(last+transfer)
            nominal, deltas = group.nominal.to_numpy(), group.delta.to_numpy()
            result = {"gamma": record["gamma"], "day": int(day), "date": str(pd.Timestamp(forecast.columns[int(day)]).date())}
            for name, durations in (("last_leg", last_times), ("full_chain", chain_times)):
                timely = np.array(durations) <= 600
                result[name] = {"nominal_ratio": float(nominal @ timely/nominal.sum()),
                                **worst_service_ratio(nominal, deltas, timely, record["gamma"]*len(group))}
            policy_results.append(result)

    # A capacity-free upper bound: each demand may use its fastest legal route.
    # If even this upper bound is below 95%, a capacity-constrained model cannot attain 95%.
    possible = []
    for customer, sku in forecast.index:
        source = cdc[sku]
        durations = []
        direct = arc(source, customer)
        if direct is not None and direct.Distance <= 5000:
            durations.append(float(direct.Duration))
        for rdc in rdcs:
            first, last = arc(source, rdc), arc(rdc, customer)
            if first is not None and last is not None and first.Distance <= 5000 and last.Distance <= 5000:
                durations.append(float(first.Duration+last.Duration))
        possible.append(bool(durations and min(durations) <= 600))
    possible = np.array(possible)
    upper_bounds = [{"date": str(pd.Timestamp(date).date()),
                     "capacity_free_full_chain_nominal_ratio_upper_bound": float(forecast[date].to_numpy() @ possible/forecast[date].sum())}
                    for date in forecast.columns]
    return {"source": str(path), "policy_comparison": policy_results, "full_chain_upper_bounds": upper_bounds,
            "scope": "Sensitivity analysis, not an official interpretation of the contest's service clock. Factory-to-CDC and handling delays are excluded."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy_json", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.policy_json.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["full_chain_upper_bounds"], ensure_ascii=False, indent=2))
