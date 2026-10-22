"""Independently reconstruct both subsidy policies from raw routes and decisions."""
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
from tools.audit_results import check_network


def audit(root):
    facilities = pd.read_csv(ROOT/'data/raw/df_wh.csv').set_index('Name')
    procurement = pd.read_csv(ROOT/'data/raw/df_proc.csv').set_index('Name')
    matrix = pd.read_csv(ROOT/'data/raw/df_matrix.csv').set_index(['From', 'To'])
    orders = pd.read_csv(ROOT/'data/raw/df_order.csv').set_index(['Name', 'SKU']).qty
    warehouses = set(facilities.index[facilities.Type.isin(['CDC', 'RDC'])])
    evidence = [json.loads(line) for line in (root/'_runs/q2-subsidy/solver_metrics.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(evidence) != 2:
        raise ValueError('Expected exactly two solver records')
    comparison = pd.read_csv(root/'question2/开仓补贴政策对比_cplex.csv').set_index('方案类型')
    if comparison.index.duplicated().any() or set(comparison.index) != {'无补贴', '有补贴'}:
        raise ValueError('Incomplete or duplicate policy comparison')
    if not np.isfinite(comparison.drop(columns=['求解状态']).to_numpy(dtype=float)).all():
        raise ValueError('Nonfinite policy comparison')
    reports = []
    for position, scenario in enumerate(('without_subsidy', 'with_subsidy')):
        folder = root/'question2/subsidy_scenarios'/scenario
        supply = pd.read_csv(folder/'flows.csv')
        decisions = pd.read_csv(folder/'decisions.csv')
        if decisions.Name.duplicated().any() or set(decisions.Name) != warehouses or not decisions[['open', 'smart']].isin([0, 1]).all().all():
            raise ValueError('Invalid warehouse decision table')
        decisions = decisions.set_index('Name')
        business_frame = pd.read_csv(folder/'business.csv')
        if len(business_frame) != 1:
            raise ValueError('Expected exactly one business row per scenario')
        business = business_frame.iloc[0]
        numeric = business.drop(labels=['方案类型', '求解状态']).to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError('Nonfinite business value')
        result = check_network(supply, orders, 'q2-subsidy/'+scenario, 1e-6)
        issues = result['issues']
        if (decisions.smart > decisions.open).any() or any(decisions.loc[wh, 'open'] != 1 for wh in facilities.index[facilities.Type.eq('CDC')]):
            issues.append('系统采购绑定或 CDC 必开违反')
        outbound = supply.groupby('source').qty.sum().reindex(decisions.index, fill_value=0)
        if any(decisions.loc[wh, 'open'] != 1 for wh in supply.source.unique()):
            issues.append('未开仓即供货')
        transport = {'transfer': 0.0, 'delivery': 0.0}
        for route in supply.itertuples(index=False):
            arc = matrix.loc[(route.source, route.target)]
            transfer = route.target in warehouses
            transport['transfer' if transfer else 'delivery'] += float(arc.Distance)*route.qty*(0.9e-4 if transfer else 1.45e-4)
        count = int(decisions.open.sum())
        subsidy = 7*max(count-10, 0) if position else 0
        components = {'仓库之间的运输总成本（单位：万元）': transport['transfer'],
                      '仓库到门店的运输总成本（单位：万元）': transport['delivery'],
                      '开仓总成本（单位：万元）': float((decisions.open*procurement.Opening_fee).sum()),
                      '出入仓处置总成本（单位：万元）': float((outbound*procurement.Processing_fee*(1-.4*decisions.smart)).sum()),
                      '智能调度系统采购总成本（单位：万元）': float(decisions.smart.sum()*1.5)}
        social = sum(components.values())
        expected = {**components, '开仓数量': count, '时效满足率': result['timeliness_ratio'],
                    '补贴金额（单位：万元）': subsidy, '社会总成本（单位：万元）': social,
                    '企业总物流成本（单位：万元）': social-subsidy}
        label = '有补贴' if position else '无补贴'
        if business['方案类型'] != label:
            issues.append('方案标签不符')
        residuals = {}
        for column, value in expected.items():
            residuals[column] = float(business[column])-value
            if abs(residuals[column]) > 1e-5 or abs(float(comparison.loc[label, column])-value) > 1e-5:
                issues.append('独立费用或对比表不一致: '+column)
        qty = pd.read_csv(folder/'warehouse_quantities.csv').set_index(['Name', 'SKU']).iloc[:, 0]
        actual = supply.groupby(['source', 'sku']).qty.sum()
        actual.index.names = qty.index.names
        if qty.subtract(actual, fill_value=0).abs().max() > 1e-6:
            issues.append('仓库处理量与实际出库量不符')
        solve = evidence[position]
        if not solve.get('has_incumbent') or abs(solve['objective']-(social-subsidy)) > 1e-5:
            issues.append('实际求解目标与独立企业成本不一致')
        result.update(open_count=count, subsidy=subsidy, social_cost=social, enterprise_cost=social-subsidy,
                      residuals=residuals, solver_status=solve['status'], relative_gap=solve.get('relative_gap'),
                      policy_scope='Existing interpretation: 7*max(total open warehouses including CDCs-10,0); final business interpretation pending.')
        reports.append(result)
    return reports


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_root', type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    reports = audit(args.result_root.resolve())
    provenance = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
                  'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'network_verifier_sha256': hashlib.sha256((ROOT/'tools/audit_results.py').read_bytes()).hexdigest(),
                  'raw_inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'data/raw').glob('*.csv'))}}
    for row in reports:
        row['audit_provenance'] = provenance
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps([{key: value for key, value in row.items() if key != 'audit_provenance'} for row in reports], ensure_ascii=False, indent=2))
    raise SystemExit(1 if any(row['issues'] for row in reports) else 0)
