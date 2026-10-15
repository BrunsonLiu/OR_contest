"""Independently check exported flows, capacities, timeliness and accounting."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from src.runtime import read_forecast


def check_network(supply, demand, label, tolerance):
    facilities = pd.read_csv(ROOT / "data/raw/df_wh.csv").set_index("Name")
    customers = pd.read_csv(ROOT / "data/raw/df_customer.csv")
    aliases = dict(zip(customers.Location, customers.Name))
    aliases.update(dict(zip(customers.Name, customers.Name)))
    supply = supply.copy()
    supply["target"] = supply.target.map(lambda target: aliases.get(target, target))
    capacities = pd.read_csv(ROOT / "data/raw/df_proc.csv").set_index("Name").Capacity
    matrix = pd.read_csv(ROOT / "data/raw/df_matrix.csv").set_index(["From", "To"])
    types = facilities.Type.to_dict()
    issues = []
    if (supply.qty < -tolerance).any() or not np.isfinite(supply.qty).all():
        issues.append("存在负数或非有限流量")
    deliveries = supply[~supply.target.isin(types)]
    actual = deliveries.groupby(["target", "sku"]).qty.sum()
    actual.index.names = demand.index.names
    difference = actual.subtract(demand, fill_value=0)
    max_demand_error = float(difference.abs().max())
    if max_demand_error > min(tolerance, 0.011):
        issues.append(f"需求与配送量不符：最大误差 {max_demand_error}")
    if deliveries.groupby(["target", "sku"]).size().gt(1).any():
        issues.append("同一门店/SKU 存在多个服务仓库")
    outgoing = supply.groupby("source").qty.sum()
    for wh, qty in outgoing.items():
        if wh not in capacities or qty > capacities.get(wh, 0) + tolerance:
            issues.append(f"仓库超容量或缺少容量：{wh}")
    for row in supply.itertuples(index=False):
        if row.source not in types:
            issues.append(f"未知供货设施：{row.source}")
            continue
        if row.target in types:
            if types[row.source] != "CDC" or types[row.target] != "RDC":
                issues.append(f"不允许的仓间调拨：{row.source} → {row.target}")
        if types[row.source] == "CDC":
            allowed = "im" if row.source == "gang-kou-CDC" else "dm"
            if row.sku != allowed:
                issues.append(f"CDC 商品类型不符：{row.source}/{row.sku}")
    for rdc in facilities[facilities.Type.eq("RDC")].index:
        for sku in ("dm", "im"):
            incoming = supply.loc[supply.target.eq(rdc) & supply.sku.eq(sku), "qty"].sum()
            leaving = supply.loc[supply.source.eq(rdc) & supply.sku.eq(sku), "qty"].sum()
            # Exported per-route quantities may each be rounded to 0.01 tonnes.
            if abs(incoming-leaving) > tolerance:
                issues.append(f"RDC 流量不平衡：{rdc}/{sku} 差值 {incoming-leaving}")
    timely = 0.0
    for row in deliveries.itertuples(index=False):
        if (row.source, row.target) not in matrix.index:
            issues.append(f"缺少路线时效：{row.source} → {row.target}")
        elif matrix.loc[(row.source, row.target), "Duration"] <= 600:
            timely += row.qty
    ratio = timely / float(demand.sum())
    if ratio < 0.95 - tolerance / float(demand.sum()):
        issues.append(f"时效满足率不足：{ratio}")
    return {"case": label, "issues": issues, "max_demand_error_tonnes": max_demand_error,
            "timeliness_ratio": ratio, "flow_rounding_tolerance_tonnes": tolerance}


def audit(result_root):
    reports = []
    q1 = result_root / "question1/仓网供应关系文件_cplex.csv"
    if q1.exists():
        supply = pd.read_csv(q1)
        supply.columns = ["source", "target", "sku", "qty"]
        orders = pd.read_csv(ROOT / "data/raw/df_order.csv").set_index(["Name", "SKU"]).qty
        reports.append(check_network(supply, orders, "q1", 1e-6))
        business = pd.read_csv(q1.parent / "仓网业务表现文件_cplex.csv").iloc[0]
        residual = float(business.iloc[2] - business.iloc[3:].sum())
        reports[-1]["cost_component_residual"] = residual
        if abs(residual) > 1e-5:
            reports[-1]["issues"].append("成本分项之和与目标值不一致")
        quantities = pd.read_csv(q1.parent / "仓库处置订单量文件_cplex.csv")
        exported = quantities.set_index(["Name", "SKU"]).iloc[:, 0]
        actual_outbound = supply.groupby(["source", "sku"]).qty.sum()
        actual_outbound.index.names = exported.index.names
        if exported.subtract(actual_outbound, fill_value=0).abs().max() > 1e-6:
            reports[-1]["issues"].append("导出处置订单量与实际出库量不符")
    forecast = read_forecast().set_index(["Customer", "SKU"])
    for version in ("problem4_noloss", "problem4_loss_v2"):
        folder = result_root / "question4" / version / "output_result"
        for day, col in enumerate(forecast.columns):
            date = pd.Timestamp(col).strftime("%Y-%m-%d")
            path = folder / f"仓网供应关系文件_{date}.csv"
            if not path.exists():
                continue
            supply = pd.read_csv(path).iloc[:, :4]
            supply.columns = ["source", "target", "sku", "qty"]
            reports.append(check_network(supply, forecast[col], f"{version}/{date}", 0.6))
    robust_path = result_root / "question4/problem4_robust/robust_results.json"
    if robust_path.exists():
        for row in json.loads(robust_path.read_text(encoding="utf-8")):
            if row.get("total_cost") is None:
                reports.append({"case": f"robust/gamma={row['gamma']}", "issues": [], "solver_status": row["status"], "has_incumbent": False})
                continue
            costs = sum(row[key] for key in ("transport_cost_customer", "transport_cost_warehouse", "proc_cost_actual", "loss_cost", "open_cost", "smart_cost"))
            residual = row["objective"] - costs - row["robust_premium"]
            issues = []
            opened = [set(warehouses) for _, warehouses in sorted(row["open_by_day"].items(), key=lambda item: int(item[0]))]
            if any(not previous.issubset(current) for previous, current in zip(opened, opened[1:])):
                issues.append("开仓变量存在先开后关")
            if abs(residual) > 1e-5 or row["robust_premium"] < -1e-5:
                issues.append("成本分解与鲁棒附加成本不一致")
            if row["gamma"] == 0 and abs(row["robust_premium"]) > 1e-5:
                issues.append("Gamma=0 时附加成本不为零")
            reports.append({"case": f"robust/gamma={row['gamma']}", "issues": issues,
                            "solver_status": row["status"], "accounting_residual": residual})
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    reports = audit(args.result_root.resolve())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = [(r["case"], r["issues"]) for r in reports if r["issues"]]
    print(f"Checked {len(reports)} result cases; cases with issues: {len(issues)}")
    for case, messages in issues:
        print(case, messages)
    raise SystemExit(1 if issues else 0)
