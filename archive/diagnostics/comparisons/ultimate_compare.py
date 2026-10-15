"""
终极对比：用同一套公式，分别计算两个模型的解的真实成本
目标：找到 233,186 vs 79,807 的 3 倍差距到底从哪来
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import os, json

BASE = str(_REPO_ROOT)

# ========== 公共数据 ==========
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

dist = {}
dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

cap = {}; open_cost = {}; proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']
    proc_cost[row['Name']] = row['Processing_fee']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand = {}
for t_idx, date_col in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = float(row[date_col])

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

# ========== 1. 确定性模型的解 ==========
print("=" * 70)
print("1. 确定性模型：从供应关系CSV重建成本")
print("=" * 70)

det_dir = f'{BASE}/results/question4/problem4_loss/output_result'
det_total_loss = 0
det_total_trans_cust = 0
det_total_trans_wh = 0
det_total_proc = 0
det_total_open = 0
det_total_smart = 0
det_total_tons = 0
det_rdc_set = set()

for t in range(T):
    date_str = forecast_dates[t]
    csv_file = f'{det_dir}/仓网供应关系文件_{date_str}.csv'
    if not os.path.exists(csv_file):
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y/%m/%-d', '%Y-%-m-%-d']:
            try:
                alt = pd.to_datetime(date_str).strftime('%Y-%m-%d')
                csv_file = f'{det_dir}/仓网供应关系文件_{alt}.csv'
                if os.path.exists(csv_file):
                    break
            except:
                pass
    if not os.path.exists(csv_file):
        print(f"  WARNING: {csv_file} not found")
        continue

    df_rel = pd.read_csv(csv_file)
    col_wh = df_rel.columns[0]
    col_to = df_rel.columns[1]
    col_sku = df_rel.columns[2]
    col_qty = df_rel.columns[3]

    day_loss = 0
    day_trans_cust = 0
    day_trans_wh = 0
    day_proc = 0
    day_tons = 0

    for _, row in df_rel.iterrows():
        wh = row[col_wh]
        to = row[col_to]
        sku = row[col_sku]
        qty = float(row[col_qty])

        d = dur.get((wh, to), dur.get((to, wh), 0))
        di = dist.get((wh, to), dist.get((to, wh), 0))
        lpt = loss_per_ton(d)

        if 'CDC' in wh:
            day_trans_wh += 0.9e-4 * di * qty
            day_loss += lpt * qty
            day_proc += 2.0 * proc_cost.get(wh, 0) * qty
        else:
            day_trans_cust += 1.45e-4 * di * qty
            day_loss += lpt * qty
            day_proc += 2.0 * proc_cost.get(wh, 0) * qty
            det_rdc_set.add(wh)
            day_tons += qty

    det_total_loss += day_loss
    det_total_trans_cust += day_trans_cust
    det_total_trans_wh += day_trans_wh
    det_total_proc += day_proc
    det_total_tons += day_tons

    print(f"  Day {t} ({forecast_dates[t]}): loss={day_loss:.0f}, trans_c={day_trans_cust:.0f}, "
          f"trans_w={day_trans_wh:.0f}, proc={day_proc:.0f}, tons={day_tons:.0f}")

det_total_open = sum(open_cost.get(w, 0) for w in det_rdc_set)
det_total_smart = 1.5 * len(det_rdc_set)
det_discount = sum(0.8 * proc_cost.get(w, 0) for w in det_rdc_set)

det_manual_total = (det_total_trans_cust + det_total_trans_wh +
                    det_total_proc + det_total_loss +
                    det_total_open + det_total_smart - det_discount)

print(f"\n  确定性模型重建成本 (我的公式):")
print(f"    运输(门): {det_total_trans_cust:.0f}")
print(f"    运输(仓): {det_total_trans_wh:.0f}")
print(f"    处置费:   {det_total_proc:.0f}")
print(f"    损耗:     {det_total_loss:.0f}")
print(f"    开仓费:   {det_total_open:.0f}")
print(f"    智能费:   {det_total_smart:.0f}")
print(f"    智能折扣: -{det_discount:.0f}")
print(f"    合计:     {det_manual_total:.0f}")
print(f"    RDC数:    {len(det_rdc_set)}")

# ========== 2. 确定性模型报告的成本 ==========
print("\n" + "=" * 70)
print("2. 确定性模型：报告的成本")
print("=" * 70)
det_summary = pd.read_csv(f'{det_dir}/仓网业务表现文件_汇总.csv')
print(det_summary.to_string())

# ========== 3. 鲁棒模型的解 ==========
print("\n" + "=" * 70)
print("3. 鲁棒模型 Γ=0%：从解重建成本")
print("=" * 70)

with open(f'{BASE}/results/question4/problem4_robust/robust_results.json', 'r', encoding='utf-8') as f:
    rob_results = json.load(f)

r0 = rob_results[0]
rob_daily = r0['daily_costs']

rob_total_loss = 0
rob_total_trans_cust = 0
rob_total_trans_wh = 0
rob_total_proc = 0
rob_total_tons = 0

for d in rob_daily:
    rob_total_trans_cust += d['transport_cust']
    rob_total_trans_wh += d['transport_wh']
    rob_total_proc += d['proc']
    rob_total_loss += d.get('loss', 0)
    rob_total_tons += d.get('tons', 0)

print(f"    运输(门): {rob_total_trans_cust:.0f}")
print(f"    运输(仓): {rob_total_trans_wh:.0f}")
print(f"    处置费:   {rob_total_proc:.0f}")
print(f"    损耗:     {rob_total_loss:.0f}")
print(f"    开仓+智能: {r0['open_cost'] + r0['smart_cost']:.0f}")
print(f"    合计:     {r0['total_cost']:.0f}")
print(f"    RDC数:    {r0['num_open']}")

# ========== 4. 逐项对比 ==========
print("\n" + "=" * 70)
print("4. 逐项对比")
print("=" * 70)
print(f"{'项目':<12} {'确定性(重建)':>12} {'鲁棒':>12} {'差距':>12} {'倍数':>6}")
print("-" * 56)

items = [
    ("运输(门)", det_total_trans_cust, rob_total_trans_cust),
    ("运输(仓)", det_total_trans_wh, rob_total_trans_wh),
    ("处置费", det_total_proc, rob_total_proc),
    ("损耗", det_total_loss, rob_total_loss),
    ("开仓+智能", det_total_open + det_total_smart - det_discount, r0['open_cost'] + r0['smart_cost']),
]

for name, det_v, rob_v in items:
    diff = det_v - rob_v
    ratio = det_v / rob_v if rob_v > 0 else float('inf')
    print(f"{name:<12} {det_v:>12.0f} {rob_v:>12.0f} {diff:>12.0f} {ratio:>6.1f}x")

# ========== 5. 损耗深度分析 ==========
print("\n" + "=" * 70)
print("5. 损耗深度分析：CDC→RDC vs RDC→门店")
print("=" * 70)

# 确定性模型：CDC→RDC 损耗
det_cdc_loss = 0
det_rdc_loss = 0
det_cdc_tons = 0
det_rdc_tons = 0

for t in range(T):
    date_str = forecast_dates[t]
    csv_file = f'{det_dir}/仓网供应关系文件_{date_str}.csv'
    if not os.path.exists(csv_file):
        alt = pd.to_datetime(date_str).strftime('%Y-%m-%d')
        csv_file = f'{det_dir}/仓网供应关系文件_{alt}.csv'
    if not os.path.exists(csv_file):
        continue

    df_rel = pd.read_csv(csv_file)
    col_wh = df_rel.columns[0]
    col_to = df_rel.columns[1]
    col_sku = df_rel.columns[2]
    col_qty = df_rel.columns[3]

    for _, row in df_rel.iterrows():
        wh = row[col_wh]
        to = row[col_to]
        sku = row[col_sku]
        qty = float(row[col_qty])

        d = dur.get((wh, to), dur.get((to, wh), 0))
        lpt = loss_per_ton(d)

        if 'CDC' in wh:
            det_cdc_loss += lpt * qty
            det_cdc_tons += qty
        else:
            det_rdc_loss += lpt * qty
            det_rdc_tons += qty

print(f"  确定性模型:")
print(f"    CDC→RDC: {det_cdc_tons:.0f} 吨, 损耗 {det_cdc_loss:.0f} 万, "
      f"均值 {det_cdc_loss/det_cdc_tons:.4f} 万/吨" if det_cdc_tons > 0 else "    CDC→RDC: 0")
print(f"    RDC→门店: {det_rdc_tons:.0f} 吨, 损耗 {det_rdc_loss:.0f} 万, "
      f"均值 {det_rdc_loss/det_rdc_tons:.4f} 万/吨" if det_rdc_tons > 0 else "    RDC→门店: 0")
print(f"    合计损耗: {det_cdc_loss + det_rdc_loss:.0f} 万")
print(f"    CDC→RDC 占比: {det_cdc_loss/(det_cdc_loss+det_rdc_loss)*100:.1f}%")

# ========== 6. 检查确定性模型的损耗公式 ==========
print("\n" + "=" * 70)
print("6. 检查确定性模型的损耗公式")
print("=" * 70)

# 读取确定性模型代码中的 calculate_loss_cost
with open(f'{BASE}/src/solvers/question4/solve_problem4_loss.py', 'r', encoding='utf-8') as f:
    det_code = f.read()

import re
# 找到 calculate_loss_cost 函数
match = re.search(r'def calculate_loss_cost\(.*?\):(.*?)(?=\ndef |\nclass |\Z)', det_code, re.DOTALL)
if match:
    func_code = match.group(0)
    print(f"  确定性模型的损耗函数:")
    for line in func_code.split('\n')[:15]:
        print(f"    {line}")

    # 检查阈值
    if '600' in func_code:
        print(f"\n  ⚠️ 发现 600！确定性模型可能也用了 TIMELINESS_THRESHOLD=600 作为损耗阈值")
    if '500' in func_code:
        print(f"  ✅ 发现 500，损耗阈值正确")
