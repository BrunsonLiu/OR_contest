# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import numpy as np
import os

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')
FORECAST_DIR = os.path.join(BASE_DIR, 'results/question3')

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(FORECAST_DIR, '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
all_wh_names = cdc_names + rdc_names
customer_cities = df_customer['Name'].tolist()

dist_oneway = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_oneway = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

dist_biway = {}
dur_biway = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist_biway[(o, d)] = row['Distance']
    dist_biway[(d, o)] = row['Distance']
    dur_biway[(o, d)] = row['Duration']
    dur_biway[(d, o)] = row['Duration']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {}
for t_idx, date_col in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = float(row[date_col])

LOSS_THRESHOLD = 500.0
def calc_loss(m):
    if m <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (m - LOSS_THRESHOLD) ** 2 / 10000.0

loss_oneway = {(f, t): calc_loss(time_oneway[(f, t)]) for f, t in time_oneway.keys()}
loss_biway = {}
for wh_name in all_wh_names:
    for c_city in customer_cities:
        loss_biway[(wh_name, c_city)] = calc_loss(dur_biway.get((wh_name, c_city), 10000))
for cdc in cdc_names:
    for rdc in rdc_names:
        loss_biway[(cdc, rdc)] = calc_loss(dur_biway.get((cdc, rdc), 10000))

cap = {}
proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']

sku_cdc = {'im': port_cdc, 'dm': inland_cdc}

print("=" * 70)
print("诊断1: 距离矩阵完整性 - u变量(wh,city)对")
print("=" * 70)

missing_oneway = 0
missing_biway = 0
zero_dist_oneway = 0
total_pairs = 0

for t in range(T):
    for (city, sku), qty in demand[t].items():
        for wh in [sku_cdc[sku]] + rdc_names:
            total_pairs += 1
            d1 = dist_oneway.get((wh, city), None)
            d2 = dist_biway.get((wh, city), None)
            if d1 is None:
                missing_oneway += 1
            if d2 is None:
                missing_biway += 1
            if d1 is None or d1 == 0:
                zero_dist_oneway += 1

print(f"  总(wh,city)对数: {total_pairs}")
print(f"  确定性模型(单向)缺失: {missing_oneway}")
print(f"  鲁棒模型(双向)缺失: {missing_biway}")
print(f"  确定性模型0距离或缺失: {zero_dist_oneway}")

print("\n" + "=" * 70)
print("诊断2: u变量空间对比")
print("=" * 70)

u_det = 0
u_rob = 0
u_det_only = []

for t in range(T):
    for (city, sku), qty in demand[t].items():
        for wh in [sku_cdc[sku]] + rdc_names:
            d_det = dist_oneway.get((wh, city), 0)
            d_rob = dist_biway.get((wh, city), 99999)
            in_det = True
            in_rob = d_rob <= 5000
            if in_det:
                u_det += 1
            if in_rob:
                u_rob += 1
            if in_det and not in_rob:
                u_det_only.append((t, wh, city, sku, d_det, d_rob))

print(f"  确定性模型u变量数: {u_det}")
print(f"  鲁棒模型u变量数: {u_rob}")
print(f"  仅确定性模型有(距离>5000km): {len(u_det_only)}")
if u_det_only:
    print(f"  示例(前10):")
    for item in u_det_only[:10]:
        t, wh, city, sku, d_det, d_rob = item
        print(f"    t={t} {wh}->{city} sku={sku} dist={d_det}/{d_rob}")

print("\n" + "=" * 70)
print("诊断3: 目标函数系数差异")
print("=" * 70)

diff_count = 0
same_count = 0
big_diffs = []

for t in range(T):
    for (city, sku), qty in demand[t].items():
        for wh in [sku_cdc[sku]] + rdc_names:
            d_det = dist_oneway.get((wh, city), 0)
            d_rob = dist_biway.get((wh, city), 99999)
            if d_rob > 5000:
                continue
            l_det = loss_oneway.get((wh, city), 0.0)
            l_rob = loss_biway.get((wh, city), 0.0)
            obj_det = 1.45e-4 * d_det * qty + l_det * qty + 2.0 * proc_cost.get(wh, 0.0) * qty
            obj_rob = 1.45e-4 * d_rob * qty + l_rob * qty + 2.0 * proc_cost.get(wh, 0.0) * qty
            if abs(obj_det - obj_rob) > 0.001:
                diff_count += 1
                if len(big_diffs) < 20:
                    big_diffs.append((t, wh, city, sku, qty, d_det, d_rob, l_det, l_rob, obj_det, obj_rob))
            else:
                same_count += 1

print(f"  u变量系数一致: {same_count}")
print(f"  u变量系数不一致: {diff_count}")
if big_diffs:
    print(f"  不一致的变量(前20):")
    for item in big_diffs:
        t, wh, city, sku, qty, d_det, d_rob, l_det, l_rob, obj_det, obj_rob = item
        print(f"    t={t} {wh}->{city} sku={sku} qty={qty:.1f}")
        print(f"      dist: det={d_det} rob={d_rob} | loss: det={l_det:.4f} rob={l_rob:.4f}")
        print(f"      obj: det={obj_det:.4f} rob={obj_rob:.4f} diff={obj_det-obj_rob:.4f}")

f_diff = 0
f_same = 0
f_diffs = []
for t in range(T):
    for cdc in cdc_names:
        s = 'im' if cdc == port_cdc else 'dm'
        for rdc in rdc_names:
            d_det = dist_oneway.get((cdc, rdc), 0)
            d_rob = dist_biway.get((cdc, rdc), 99999)
            if d_rob > 5000:
                continue
            l_det = loss_oneway.get((cdc, rdc), 0.0)
            l_rob = loss_biway.get((cdc, rdc), 0.0)
            obj_det = 0.9e-4 * d_det + l_det + 2.0 * proc_cost.get(cdc, 0.0)
            obj_rob = 0.9e-4 * d_rob + l_rob + 2.0 * proc_cost.get(cdc, 0.0)
            if abs(obj_det - obj_rob) > 0.001:
                f_diff += 1
                if len(f_diffs) < 20:
                    f_diffs.append((t, cdc, rdc, s, d_det, d_rob, l_det, l_rob, obj_det, obj_rob))
            else:
                f_same += 1

print(f"\n  f变量系数一致: {f_same}")
print(f"  f变量系数不一致: {f_diff}")
if f_diffs:
    print(f"  不一致的f变量(前20):")
    for item in f_diffs:
        t, cdc, rdc, s, d_det, d_rob, l_det, l_rob, obj_det, obj_rob = item
        print(f"    t={t} {cdc}->{rdc} sku={s}")
        print(f"      dist: det={d_det} rob={d_rob} | loss: det={l_det:.4f} rob={l_rob:.4f}")
        print(f"      obj: det={obj_det:.4f} rob={obj_rob:.4f} diff={obj_det-obj_rob:.4f}")

print("\n" + "=" * 70)
print("诊断4: 0距离/0损耗的u变量(被CPLEX选中的风险)")
print("=" * 70)

zero_vars = []
for t in range(T):
    for (city, sku), qty in demand[t].items():
        for wh in [sku_cdc[sku]] + rdc_names:
            d = dist_oneway.get((wh, city), 0)
            l = loss_oneway.get((wh, city), 0.0)
            if d == 0 and l == 0:
                obj = 2.0 * proc_cost.get(wh, 0.0) * qty
                zero_vars.append((t, wh, city, sku, qty, obj))

print(f"  0距离+0损耗的u变量数: {len(zero_vars)}")
if zero_vars:
    seen = set()
    for item in zero_vars:
        t, wh, city, sku, qty, obj = item
        key = (wh, city, sku)
        if key not in seen:
            seen.add(key)
            is_self = city in wh or wh.replace('-CDC', '').replace('-DC', '') in city
            print(f"    {wh}->{city} sku={sku} qty={qty:.1f} obj={obj:.4f} same_loc={is_self}")

print("\n" + "=" * 70)
print("诊断5: 容量值对比")
print("=" * 70)
for wh in all_wh_names:
    print(f"  {wh}: cap={cap.get(wh, 'N/A')} proc={proc_cost.get(wh, 'N/A')}")

print("\n" + "=" * 70)
print("诊断6: 关键差异总结")
print("=" * 70)
print(f"""
1. 距离矩阵: 确定性单向 vs 鲁棒双向
   - 缺失u变量条目: 确定性{missing_oneway} vs 鲁棒{missing_biway}
   - 0距离/缺失条目: 确定性{zero_dist_oneway}

2. u变量数: 确定性{u_det} vs 鲁棒{u_rob}
   - 仅确定性有(>5000km): {len(u_det_only)}

3. 目标系数差异:
   - u变量: {diff_count}个不一致
   - f变量: {f_diff}个不一致

4. 0成本u变量: {len(zero_vars)}个
   - 这些变量只有处置成本,没有运输和损耗成本
   - CPLEX可能错误地选中这些变量
""")
