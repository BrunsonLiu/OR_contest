"""Independently check exported flows, capacities, timeliness and accounting."""
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
from src.runtime import read_forecast, forecast_path
from scipy.optimize import linprog


def check_robust_policy(row, forecast):
    """Rebuild costs and worst violations from raw inputs, using separate LPs."""
    policy = pd.DataFrame(row["assignment_policy"])
    procurement = pd.read_csv(ROOT / "data/raw/df_proc.csv").set_index("Name")
    facilities = pd.read_csv(ROOT / "data/raw/df_wh.csv").set_index("Name").Type.to_dict()
    matrix = pd.read_csv(ROOT / "data/raw/df_matrix.csv").set_index(["From", "To"])
    history = pd.read_csv(ROOT / "data/raw/df_past_order.csv").set_index(["Name", "SKU"])
    weekdays = pd.to_datetime(history.columns, format="%Y/%m/%d").dayofweek
    residual_stds = {}
    for key, values in history.iterrows():
        array = values.to_numpy(float)
        residuals = array - np.array([array[weekdays == day].mean() for day in weekdays])
        residual_stds[key] = max(float(residuals.std(ddof=1)), 0.01)
    factors = {0: 1.15, 1: 0.9, 2: 0.9, 3: 0.9, 4: 1.15, 5: 1.15, 6: 1.15}
    cdc_by_sku = {"dm": "nei-lu-CDC", "im": "gang-kou-CDC"}
    smart = set(row["smart_warehouses"])
    opened_union = set().union(*(set(names) for names in row["open_by_day"].values()))
    issues = []
    if any(facilities.get(wh) != "CDC" and wh not in opened_union for wh in smart):
        issues.append("未开设的仓库采购了系统")
    total_nominal, total_extra = 0.0, 0.0
    minimum_capacity_slack = float("inf")
    maximum_time_deficit = -float("inf")

    def support(coefficients, budget):
        if budget == 0:
            return 0.0
        solution = linprog(-np.asarray(coefficients), A_ub=[np.ones(len(coefficients))],
                           b_ub=[budget], bounds=(0, 1), method="highs")
        if not solution.success:
            raise RuntimeError("独立不确定集 LP 求解失败")
        return -float(solution.fun)

    def arc(origin, destination):
        key = (origin, destination) if (origin, destination) in matrix.index else (destination, origin)
        return matrix.loc[key]

    def loss(duration):
        return 0.2*max(float(duration)-500, 0)**2/10000

    for day, date in enumerate(forecast.columns):
        group = policy[policy.day.eq(day)]
        if group.duplicated(["customer", "sku"]).any() or set(zip(group.customer, group.sku)) != set(forecast.index):
            issues.append(f"day={day} 配送关系缺失或重复")
            continue
        opened_today = set(row["open_by_day"][str(day)])
        nominal, delta, units, timely, assignments, skus = [], [], [], [], [], []
        for route in group.itertuples(index=False):
            key = (route.customer, route.sku)
            qty = float(forecast.loc[key, date])
            radius = residual_stds[key]*2*factors[pd.Timestamp(date).weekday()]
            if abs(qty-route.nominal) > 1e-7 or abs(radius-route.delta) > 1e-7:
                issues.append(f"day={day} 需求或偏差与输入不符")
            wh, cdc = route.warehouse, cdc_by_sku[route.sku]
            if wh != cdc and facilities.get(wh) != "RDC":
                issues.append("配送来源不符合 CDC/SKU 规则")
            if facilities.get(wh) == "RDC" and wh not in opened_today:
                issues.append("未开仓即配送")
            delivery = arc(wh, route.customer)
            unit = 1.45e-4*delivery.Distance + loss(delivery.Duration)
            unit += procurement.loc[wh, "Processing_fee"]*(0.6 if wh in smart else 1)
            if wh != cdc:
                transfer = arc(cdc, wh)
                unit += 0.9e-4*transfer.Distance + loss(transfer.Duration)
                unit += procurement.loc[cdc, "Processing_fee"]*(0.6 if cdc in smart else 1)
            on_time = delivery.Duration <= 600
            if bool(route.on_time) != on_time:
                issues.append("导出准时标记与路网不符")
            nominal.append(qty)
            delta.append(radius)
            units.append(float(unit))
            timely.append(on_time)
            assignments.append(wh)
            skus.append(route.sku)
        nominal, delta, units = np.array(nominal), np.array(delta), np.array(units)
        budget = row["gamma"]*len(nominal)
        total_nominal += float(nominal @ units)
        total_extra += support(delta*units, budget)
        signs = 0.95-np.array(timely)
        deficit = float(signs @ nominal) + support(signs*delta, budget)
        maximum_time_deficit = max(maximum_time_deficit, deficit)
        if deficit > 1e-5:
            issues.append(f"day={day} 存在违反 95% 时效比例的需求情景")
        for wh in procurement.index:
            if facilities.get(wh) not in ("CDC", "RDC"):
                continue
            if facilities[wh] == "CDC":
                mask = np.array([cdc_by_sku[sku] == wh for sku in skus])
            else:
                mask = np.array([assigned == wh for assigned in assignments])
            worst_outbound = float(nominal @ mask) + support(delta*mask, budget)
            slack = float(procurement.loc[wh, "Capacity"])-worst_outbound
            minimum_capacity_slack = min(minimum_capacity_slack, slack)
            if slack < -1e-5:
                issues.append(f"day={day} {wh} 最坏情景超容量")
    fixed_opening = float(procurement.loc[list(opened_union), "Opening_fee"].sum())
    policy_cost = total_nominal + total_extra + fixed_opening + 1.5*len(smart)
    tolerance = max(1e-5, abs(policy_cost)*1e-8)
    if abs(policy_cost-row["policy_worst_case_cost"]) > tolerance:
        issues.append("独立 LP 重建的最坏净成本与导出策略成本不符")
    if row["objective"] < policy_cost-tolerance:
        issues.append("模型目标值低于实际策略最坏净成本")
    return {"policy_issues": issues, "independent_worst_case_cost": policy_cost,
            "model_policy_residual": row["objective"]-policy_cost,
            "minimum_capacity_slack": minimum_capacity_slack,
            "maximum_service_deficit": maximum_time_deficit}


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


def audit(result_root, forecast_override=None):
    reports = []
    q2 = result_root / "question2/仓网供应关系文件_运输损耗_cplex.csv"
    if q2.exists():
        supply = pd.read_csv(q2)
        supply.columns = ["source", "target", "sku", "qty"]
        orders = pd.read_csv(ROOT/"data/raw/df_order.csv").set_index(["Name", "SKU"]).qty
        checked = check_network(supply, orders, "q2-loss", 1e-6)
        reports.append(checked)
        issues = checked["issues"]
        customers = pd.read_csv(ROOT/"data/raw/df_customer.csv")
        aliases = dict(zip(customers.Location, customers.Name))
        supply["target"] = supply.target.map(lambda name: aliases.get(name, name))
        procurement = pd.read_csv(ROOT/"data/raw/df_proc.csv").set_index("Name")
        facilities = pd.read_csv(ROOT/"data/raw/df_wh.csv").set_index("Name")
        matrix = pd.read_csv(ROOT/"data/raw/df_matrix.csv").set_index(["From", "To"])
        business = pd.read_csv(q2.parent/"仓网业务表现文件_运输损耗_cplex.csv").iloc[0]
        if not np.isfinite(business.to_numpy(dtype=float)).all():
            raise ValueError("问题二费用表包含非有限数值，不能验收")
        amounts = {"transfer": 0.0, "delivery": 0.0, "loss": 0.0}
        for route in supply.itertuples(index=False):
            arc = matrix.loc[(route.source, route.target)]
            loss = 0.2*max(float(arc.Duration)-500, 0)**2/10000*route.qty
            transfer = facilities.Type.get(route.target) == "RDC"
            amounts["transfer" if transfer else "delivery"] += (0.9e-4 if transfer else 1.45e-4)*arc.Distance*route.qty+loss
            amounts["loss"] += loss
        residuals = {key: float(business[column])-amounts[key] for key, column in (
            ("transfer", "仓库之间的运输总成本（单位：万元）"),
            ("delivery", "仓库到门店的运输总成本（单位：万元）"),
            ("loss", "运输损耗总成本（单位：万元）"))}
        if any(abs(value) > 1e-5 for value in residuals.values()):
            issues.append("运输或损耗与原始路网独立重算不一致")
        total = float(business.iloc[3:8].sum())  # Transport columns already include loss.
        residuals["total_components"] = float(business["总物流成本（单位：万元）"])-total
        if abs(residuals["total_components"]) > 1e-5:
            issues.append("成本分解不一致，运输列已含损耗，不应再次叠加损耗列")
        if abs(float(business["时效满足率"])-checked["timeliness_ratio"]) > 1e-7:
            issues.append("导出时效比例与逐路线重算不一致")
        detail_count = 0
        for filename, destination in (("仓→仓损耗明细文件_完整版_cplex.csv", "To_wh"),
                                      ("仓→店损耗明细文件_完整版_cplex.csv", "To_store")):
            details = pd.read_csv(q2.parent/filename)
            numeric = ["Qty（单位：吨）", "运输时间(分钟)", "单吨损耗成本(万元)", "总损耗成本(万元)"]
            if not np.isfinite(details[numeric].to_numpy(dtype=float)).all():
                raise ValueError(f"损耗明细包含非有限数值: {filename}")
            rows = details.rename(columns={"From_wh": "source", destination: "target", "SKU": "sku", "Qty（单位：吨）": "qty"})
            expected_rows = supply[supply.target.isin(facilities.index)] if destination == "To_wh" else supply[~supply.target.isin(facilities.index)]
            if rows.duplicated(["source", "target", "sku"]).any() or set(zip(rows.source, rows.target, rows.sku)) != set(zip(expected_rows.source, expected_rows.target, expected_rows.sku)):
                issues.append(f"损耗明细路线缺失或重复: {filename}")
                continue
            expected_qty = expected_rows.set_index(["source", "target", "sku"]).qty
            for _, row in rows.iterrows():
                arc = matrix.loc[(row.source, row.target)]
                unit_loss = 0.2*max(float(arc.Duration)-500, 0)**2/10000
                if (abs(row.qty-expected_qty.loc[(row.source, row.target, row.sku)]) > 1e-6
                        or abs(row["运输时间(分钟)"]-arc.Duration) > 1e-7
                        or abs(row["单吨损耗成本(万元)"]-unit_loss) > 0.00000051
                        or abs(row["总损耗成本(万元)"]-row.qty*unit_loss) > 0.000051):
                    issues.append(f"损耗明细与原始路网或配送量不一致: {filename}")
                    break
            detail_count += len(rows)
        checked["loss_detail_rows_checked"] = detail_count
        outgoing = supply.groupby(["source", "sku"]).qty.sum()
        quantities = pd.read_csv(q2.parent/"仓库处置订单量文件_运输损耗_cplex.csv").set_index(["Name", "SKU"]).iloc[:, 0]
        outgoing.index.names = quantities.index.names
        if quantities.subtract(outgoing, fill_value=0).abs().max() > 1e-6:
            issues.append("处置订单量与逐路线出库量不一致")
        decisions_path = q2.parent/"仓库决策文件_运输损耗_cplex.csv"
        checked["smart_policy_checked"] = decisions_path.exists()
        if decisions_path.exists():
            decisions = pd.read_csv(decisions_path)
            expected = set(facilities.index[facilities.Type.isin(["CDC", "RDC"])])
            if decisions.Name.duplicated().any() or set(decisions.Name) != expected or not decisions[["open", "smart"]].isin([0, 1]).all().all():
                raise ValueError("仓库决策缺失、重复或非二元")
            decisions = decisions.set_index("Name")
            if (decisions.smart > decisions.open).any() or any(decisions.loc[wh, "open"] != 1 for wh in facilities.index[facilities.Type.eq("CDC")]):
                issues.append("系统采购与开仓绑定或 CDC 必开约束违反")
            if any(decisions.loc[wh, "open"] != 1 for wh in outgoing.index.get_level_values(0)):
                issues.append("未开仓即配送")
            volume = supply.groupby("source").qty.sum().reindex(decisions.index, fill_value=0)
            expected_costs = {
                "出入仓处置总成本（单位：万元）": float((volume*procurement.Processing_fee*(1-0.4*decisions.smart)).sum()),
                "开仓总成本（单位：万元）": float((decisions.open*procurement.Opening_fee).sum()),
                "智能调度系统采购总成本（单位：万元）": float(decisions.smart.sum()*1.5),
                "开仓数量": int(decisions.open.sum())}
            for column, expected_value in expected_costs.items():
                residuals[column] = float(business[column])-expected_value
                if abs(residuals[column]) > 1e-5:
                    issues.append(f"独立决策重算不一致: {column}")
        else:
            checked["limitations"] = ["缺少仓库开设/系统采购决策，不能独立验证折扣分配"]
        evidence_path = result_root/"_runs/q2-loss/solver_metrics.jsonl"
        if evidence_path.exists():
            evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
            if len(evidence) != 1 or not evidence[0].get("has_incumbent") or abs(evidence[0]["objective"]-business["总物流成本（单位：万元）"]) > 1e-5:
                issues.append("导出总成本与真实求解目标不一致")
        checked["cost_residuals"] = residuals
        checked["cost_scope"] = "Transport columns include loss; loss column is a non-additive breakdown."

    def task_forecast(task):
        manifest_path = result_root / "_runs" / task / "run.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        expected_hash = manifest.get("forecast_sha256")
        path = Path(forecast_override) if forecast_override is not None else Path(manifest.get("forecast_file", forecast_path()))
        if not path.exists() and forecast_override is None:
            path = forecast_path()
        if expected_hash and hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"{task} 预测输入指纹不匹配，请用 --forecast-file 提供原始预测文件")
        return read_forecast(path).set_index(["Customer", "SKU"])
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
    for version in ("problem4_noloss", "problem4_loss_v2"):
        folder = result_root / "question4" / version / "output_result"
        if not folder.exists():
            continue
        forecast = task_forecast("q4-no-loss" if version == "problem4_noloss" else "q4-loss")
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
        forecast = task_forecast("q4-robust")
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
            policy_report = check_robust_policy(row, forecast) if "assignment_policy" in row else {}
            issues.extend(policy_report.get("policy_issues", []))
            reports.append({"case": f"robust/gamma={row['gamma']}", "issues": issues,
                            "solver_status": row["status"], "accounting_residual": residual,
                            "policy_checked": bool(policy_report), **policy_report})
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--forecast-file", type=Path, help="原运行使用的预测文件；默认按运行清单定位")
    args = parser.parse_args()
    reports = audit(args.result_root.resolve(), args.forecast_file)
    if not reports:
        raise SystemExit("FAIL: 未找到可核查结果，不能把零检查项判为通过")
    provenance = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, *sys.argv],
                  "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "raw_inputs_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                        for path in sorted((ROOT/"data/raw").glob("*.csv"))}}
    for report in reports:
        report["audit_provenance"] = provenance
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    issues = [(r["case"], r["issues"]) for r in reports if r["issues"]]
    incomplete = [(r["case"], r["limitations"]) for r in reports if r.get("limitations")]
    print(f"Checked {len(reports)} result cases; cases with issues: {len(issues)}; incomplete evidence: {len(incomplete)}")
    for case, messages in issues:
        print(case, messages)
    for case, limitations in incomplete:
        print("INCOMPLETE", case, limitations)
    raise SystemExit(1 if issues else 2 if incomplete else 0)
