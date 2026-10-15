"""检查确定性模型中 CDC 直接服务门店的情况"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd, os

BASE = str(_REPO_ROOT)
det_dir = f'{BASE}/results/question4/problem4_loss/output_result'

df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
dur = {}
for _, r in df_matrix.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

forecast_dates = ['2016-06-24','2016-06-25','2016-06-26','2016-06-27',
                  '2016-06-28','2016-06-29','2016-06-30']

cdc_direct_tons = 0
rdc_direct_tons = 0
cdc_direct_loss = 0
rdc_direct_loss = 0

for date in forecast_dates:
    csv_file = f'{det_dir}/仓网供应关系文件_{date}.csv'
    if not os.path.exists(csv_file):
        continue
    df = pd.read_csv(csv_file)
    col_wh = df.columns[0]
    col_to = df.columns[1]
    col_sku = df.columns[2]
    col_qty = df.columns[3]

    for _, row in df.iterrows():
        wh = row[col_wh]
        to = row[col_to]
        qty = float(row[col_qty])
        d = dur.get((wh, to), dur.get((to, wh), 0))

        if 'CDC' in wh and 'DC' in to and 'CDC' not in to:
            # CDC → RDC 调拨
            pass
        elif 'CDC' in wh:
            # CDC 直接服务门店!
            lpt = 0.2*(max(0,d-500))**2/10000 if d > 500 else 0
            cdc_direct_tons += qty
            cdc_direct_loss += lpt * qty
            print(f"  CDC直送! {wh} → {to}, qty={qty:.1f}t, dur={d}min, loss={lpt:.4f}万/吨")
        else:
            # RDC → 门店
            lpt = 0.2*(max(0,d-500))**2/10000 if d > 500 else 0
            rdc_direct_tons += qty
            rdc_direct_loss += lpt * qty

print(f"\n  CDC 直送门店: {cdc_direct_tons:.0f} 吨, 损耗 {cdc_direct_loss:.0f} 万")
print(f"  RDC 送门店:   {rdc_direct_tons:.0f} 吨, 损耗 {rdc_direct_loss:.0f} 万")

# 再看鲁棒模型
print("\n" + "=" * 70)
print("鲁棒模型 Γ=0%: CDC直送门店情况")
print("=" * 70)

import json, cplex as cpx

# 直接从结果JSON读取
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json','r',encoding='utf-8') as f:
    rob = json.load(f)

r0 = rob[0]
daily = r0['daily_costs']

# 需要重新跑模型提取u变量... 太慢
# 换个方式：从汇总数据推断
print(f"  总损耗: {r0['loss_cost']:.0f}")
print(f"  运输(仓): {r0['transport_cost_warehouse']:.0f}")
print(f"  运输(门): {r0['transport_cost_customer']:.0f}")

# 简单估算：鲁棒模型CDC→RDC损耗
# 如果运输(仓)全是CDC→RDC，按平均损耗率估算
print(f"\n  如果CDC→RDC平均损耗率同确定性模型(2.34万/吨):")
print(f"    估算CDC→RDC损耗 = {r0['transport_cost_warehouse']/0.00009 * 2.34:.0f} 万 (不合理，换算法)")

# 换算法：鲁棒模型的运输(仓)成本 = 0.9e-4 * dist * qty
# 损耗 = loss_per_ton * qty
# 需要知道qty和dist... 从daily_costs推
rob_cdc_loss_est = 0
rob_rdc_loss_est = 0
for d in daily:
    rob_cdc_loss_est += d.get('loss_wh', 0)
    rob_rdc_loss_est += d.get('loss_cust', 0)

if rob_cdc_loss_est == 0 and rob_rdc_loss_est == 0:
    print(f"  JSON中无分项损耗数据，从总量推算:")
    total_loss = r0['loss_cost']
    print(f"    总损耗 {total_loss:.0f} 万")
    print(f"    如果CDC→RDC占92.3%(同确定性): {total_loss*0.923:.0f} 万")
    print(f"    如果CDC→RDC占50%: {total_loss*0.5:.0f} 万")
