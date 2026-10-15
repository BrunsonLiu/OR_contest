# -*- coding: utf-8 -*-
"""
诊断脚本：对比确定性模型 vs 鲁棒模型(Gamma=0%)的差异
找出3.8%差距(233,950 vs 225,123)的根源
"""
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
import json

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

# ========== 1. 加载数据 ==========
df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

# ========== 2. 距离矩阵对比 ==========
print("=" * 70)
print("检查1: 距离矩阵方向完整性")
print("=" * 70)

# 确定性模型方式：只存一个方向
dist_det = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
time_det = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

# 鲁棒模型方式：存两个方向
dist_rob = {}
dur_rob = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist_rob[(o, d)] = row['Distance']
    dist_rob[(d, o)] = row['Distance']
    dur_rob[(o, d)] = row['Duration']
    dur_rob[(d, o)] = row['Duration']

print(f"  确定性模型距离条目: {len(dist_det)}")
print(f"  鲁棒模型距离条目: {len(dist_rob)}")
print(f"  差异: {len(dist_rob) - len(dist_det)} 条 (双向 vs 单向)")

# 检查反向缺失
missing_reverse = []
for (o, d) in dist_det:
    if (d, o) not in dist_det:
        missing_reverse.append((o, d))
print(f"  反向缺失条目: {len(missing_reverse)}")
if missing_reverse[:5]:
    for o, d in missing_reverse[:5]:
        print(f"    有({o}→{d}) 但无({d}→{o})")

# ========== 3. 需求键对比 ==========
print("\n" + "=" * 70)
print("检查2: 需求键(Customer)与距离矩阵键的匹配")
print("=" * 70)

forecast_customers = df_forecast['Customer'].unique().tolist()
matrix_tos = df_matrix['To'].unique().tolist()
matrix_froms = df_matrix['From'].unique().tolist()
all_matrix_locs = set(matrix_tos + matrix_froms)

print(f"  预测文件Customer数: {len(forecast_customers)}")
print(f"  距离矩阵Location数: {len(all_matrix_locs)}")

# 检查预测文件中的Customer是否都在距离矩阵中
missing_in_matrix = [c for c in forecast_customers if c not in all_matrix_locs]
print(f"  预测Customer不在距离矩阵中: {len(missing_in_matrix)}")
if missing_in_matrix:
    print(f"    缺失: {missing_in_matrix[:10]}")

# 检查仓库→Customer的距离是否存在
all_wh = cdc_names + rdc_names
missing_wh_customer_det = []
missing_wh_customer_rob = []
for wh in all_wh:
    for c in forecast_customers:
        if (wh, c) not in dist_det:
            missing_wh_customer_det.append((wh, c))
        if (wh, c) not in dist_rob:
            missing_wh_customer_rob.append((wh, c))

print(f"\n  仓库→Customer距离缺失(确定性模型): {len(missing_wh_customer_det)}")
print(f"  仓库→Customer距离缺失(鲁棒模型): {len(missing_wh_customer_rob)}")
if missing_wh_customer_det:
    print(f"  *** 确定性模型用dist.get((wh,c),0) → 这些路线运输成本=0! ***")
    for wh, c in missing_wh_customer_det[:10]:
        print(f"    缺失: ({wh}, {c})")

# 检查CDC→RDC的距离
missing_cdc_rdc_det = []
missing_cdc_rdc_rob = []
for cdc in cdc_names:
    for rdc in rdc_names:
        if (cdc, rdc) not in dist_det:
            missing_cdc_rdc_det.append((cdc, rdc))
        if (cdc, rdc) not in dist_rob:
            missing_cdc_rdc_rob.append((cdc, rdc))

print(f"\n  CDC→RDC距离缺失(确定性模型): {len(missing_cdc_rdc_det)}")
print(f"  CDC→RDC距离缺失(鲁棒模型): {len(missing_cdc_rdc_rob)}")
if missing_cdc_rdc_det:
    print(f"  *** 确定性模型用dist.get((cdc,rdc),0) → 这些调拨运输成本=0! ***")
    for cdc, rdc in missing_cdc_rdc_det:
        print(f"    缺失: ({cdc}, {rdc})")

# ========== 4. 损耗成本矩阵对比 ==========
print("\n" + "=" * 70)
print("检查3: 损耗成本矩阵差异")
print("=" * 70)

LOSS_THRESHOLD = 500.0

def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

# 确定性模型方式
loss_det = {(f, t): calc_loss(time_det[(f, t)]) for f, t in time_det.keys()}

# 鲁棒模型方式
loss_rob = {}
customer_cities = list(df_customer['Name'])
for wh in all_wh:
    for c in customer_cities:
        tt = dur_rob.get((wh, c), 10000)
        loss_rob[(wh, c)] = calc_loss(tt)
for cdc in cdc_names:
    for rdc in rdc_names:
        tt = dur_rob.get((cdc, rdc), 10000)
        loss_rob[(cdc, rdc)] = calc_loss(tt)

# 检查关键路线的损耗差异
print(f"  确定性模型损耗条目: {len(loss_det)}")
print(f"  鲁棒模型损耗条目: {len(loss_rob)}")

# 对比u变量路线的损耗
diff_count = 0
diff_examples = []
for wh in all_wh:
    for c in forecast_customers:
        det_val = loss_det.get((wh, c), None)
        rob_val = loss_rob.get((wh, c), None)
        if det_val is None and rob_val is not None:
            diff_count += 1
            if len(diff_examples) < 5:
                diff_examples.append((wh, c, "缺失(→0)", rob_val))
        elif det_val is not None and rob_val is not None and abs(det_val - rob_val) > 1e-6:
            diff_count += 1
            if len(diff_examples) < 5:
                diff_examples.append((wh, c, det_val, rob_val))

print(f"  损耗值差异条目: {diff_count}")
for ex in diff_examples:
    print(f"    ({ex[0]}, {ex[1]}): 确定性={ex[2]}, 鲁棒={ex[3]}")

# ========== 5. 需求列名对比 ==========
print("\n" + "=" * 70)
print("检查4: 需求文件列名解析差异")
print("=" * 70)

det_periods = df_forecast.columns[2:]
rob_periods = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]

print(f"  确定性模型列[2:]: {list(det_periods)}")
print(f"  鲁棒模型过滤列: {list(rob_periods)}")
print(f"  是否一致: {list(det_periods) == list(rob_periods)}")

if list(det_periods) != list(rob_periods):
    only_det = [c for c in det_periods if c not in rob_periods]
    only_rob = [c for c in rob_periods if c not in det_periods]
    print(f"  仅确定性模型有: {only_det}")
    print(f"  仅鲁棒模型有: {only_rob}")

# ========== 6. 容量值对比 ==========
print("\n" + "=" * 70)
print("检查5: 容量值对比")
print("=" * 70)

cap_det = {}
proc_cost_det = {}
open_cost_det = {}
proc_dict = {}
for _, row in df_proc.iterrows():
    proc_dict[row['Name']] = {
        'Capacity': row['Capacity'],
        'Opening_fee': row['Opening_fee'],
        'Processing_fee': row['Processing_fee']
    }
for _, row in df_wh.iterrows():
    wh_name = row['Name']
    wh_type = row['Type']
    if wh_type in ['RDC', 'CDC'] and wh_name in proc_dict:
        cap_det[wh_name] = proc_dict[wh_name]['Capacity']
        proc_cost_det[wh_name] = proc_dict[wh_name]['Processing_fee']
        open_cost_det[wh_name] = proc_dict[wh_name]['Opening_fee']

cap_rob = {}
proc_cost_rob = {}
open_cost_rob = {}
for _, row in df_proc.iterrows():
    cap_rob[row['Name']] = row['Capacity']
    proc_cost_rob[row['Name']] = row['Processing_fee']
    open_cost_rob[row['Name']] = row['Opening_fee']

print(f"  确定性模型容量条目: {len(cap_det)}")
print(f"  鲁棒模型容量条目: {len(cap_rob)}")

# 检查缺失
for wh in all_wh:
    if wh not in cap_det:
        print(f"  *** 确定性模型缺失容量: {wh} (默认0, 仓库不可用!) ***")
    if wh not in cap_rob:
        print(f"  *** 鲁棒模型缺失容量: {wh} (默认5000) ***")
    if wh in cap_det and wh in cap_rob:
        if abs(cap_det[wh] - cap_rob[wh]) > 0.01:
            print(f"  容量不一致: {wh}, 确定性={cap_det[wh]}, 鲁棒={cap_rob[wh]}")

# ========== 7. 确定性模型默认0距离的影响评估 ==========
print("\n" + "=" * 70)
print("检查6: 确定性模型默认0距离的影响(关键!)")
print("=" * 70)

# 计算如果距离缺失，确定性模型会省多少运输+损耗成本
forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

total_demand = {}
for t_idx, date_col in enumerate(forecast_dates):
    total_demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        city = row['Customer']
        sku = row['SKU']
        qty = float(row[date_col])
        total_demand[t_idx][(city, sku)] = qty

# 检查每个需求点的距离是否可用
missing_cost_impact = 0
missing_routes = []
for t in range(T):
    for (city, sku), qty in total_demand[t].items():
        eligible_whs = [port_cdc] + rdc_names if sku == 'im' else [inland_cdc] + rdc_names
        for wh in eligible_whs:
            dist_val = dist_det.get((wh, city), None)
            if dist_val is None:
                # 确定性模型会用0
                trans_cost_zero = 0
                # 鲁棒模型会用99999km
                trans_cost_real = 1.45e-4 * 99999 * qty
                time_val = time_det.get((wh, city), None)
                loss_zero = 0
                loss_real = calc_loss(10000) * qty  # 默认10000分钟
                cost_diff = (trans_cost_real + loss_real) - (trans_cost_zero + loss_zero)
                missing_cost_impact += cost_diff
                if len(missing_routes) < 10:
                    missing_routes.append((t, wh, city, sku, qty, cost_diff))

print(f"  缺失距离路线数: {len(missing_routes)}")
print(f"  缺失距离导致的成本差异(总量级): {missing_cost_impact:.2f} 万元")
for r in missing_routes:
    print(f"    t={r[0]}, {r[1]}→{r[2]}({r[3]}), qty={r[4]:.2f}, 单条影响={r[5]:.4f}")

# ========== 8. 检查df_customer的Name vs 预测文件的Customer ==========
print("\n" + "=" * 70)
print("检查7: df_customer.Name vs 预测文件.Customer")
print("=" * 70)

customer_names = df_customer['Name'].unique().tolist()
forecast_customer_names = df_forecast['Customer'].unique().tolist()

only_in_customer = [c for c in customer_names if c not in forecast_customer_names]
only_in_forecast = [c for c in forecast_customer_names if c not in customer_names]

print(f"  df_customer.Name数: {len(customer_names)}")
print(f"  预测文件.Customer数: {len(forecast_customer_names)}")
print(f"  仅df_customer有: {len(only_in_customer)}")
if only_in_customer[:5]:
    print(f"    {only_in_customer[:5]}")
print(f"  仅预测文件有: {len(only_in_forecast)}")
if only_in_forecast[:5]:
    print(f"    {only_in_forecast[:5]}")

# ========== 9. 加载鲁棒模型结果 ==========
print("\n" + "=" * 70)
print("检查8: 鲁棒模型Gamma=0%结果")
print("=" * 70)

robust_result_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust', 'robust_results.json')
if os.path.exists(robust_result_file):
    with open(robust_result_file, 'r', encoding='utf-8') as f:
        robust_results = json.load(f)
    gamma0 = robust_results[0]
    print(f"  Gamma=0% 总成本: {gamma0.get('total_cost', 'N/A')}")
    print(f"  开仓数: {gamma0.get('num_open', 'N/A')}")
    print(f"  仓库列表: {gamma0.get('open_warehouses', 'N/A')}")
    print(f"  运输(门): {gamma0.get('transport_cost_customer', 0):.2f}")
    print(f"  运输(仓): {gamma0.get('transport_cost_warehouse', 0):.2f}")
    print(f"  处置费: {gamma0.get('proc_cost_actual', 0):.2f}")
    print(f"  损耗: {gamma0.get('loss_cost', 0):.2f}")
    print(f"  开仓费: {gamma0.get('open_cost', 0):.2f}")
    print(f"  智能费: {gamma0.get('smart_cost', 0):.2f}")
else:
    print(f"  鲁棒模型结果文件不存在: {robust_result_file}")

# ========== 10. 加载确定性模型结果 ==========
print("\n" + "=" * 70)
print("检查9: 确定性模型结果")
print("=" * 70)

det_summary_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result', '仓网业务表现文件_汇总.csv')
if os.path.exists(det_summary_file):
    df_det = pd.read_csv(det_summary_file, encoding='utf-8-sig')
    print(df_det.to_string())
else:
    print(f"  确定性模型结果文件不存在: {det_summary_file}")

# ========== 11. 关键差异汇总 ==========
print("\n" + "=" * 70)
print("汇总: 确定性模型 vs 鲁棒模型关键差异")
print("=" * 70)

differences = []

if len(missing_wh_customer_det) > 0:
    differences.append(f"BUG1: 确定性模型有{len(missing_wh_customer_det)}条仓库→客户距离缺失，默认0(免费运输!)")
else:
    differences.append("OK: 无仓库→客户距离缺失")

if len(missing_cdc_rdc_det) > 0:
    differences.append(f"BUG2: 确定性模型有{len(missing_cdc_rdc_det)}条CDC→RDC距离缺失，默认0(免费调拨!)")
else:
    differences.append("OK: 无CDC→RDC距离缺失")

if list(det_periods) != list(rob_periods):
    differences.append(f"BUG3: 需求列名解析不同! 确定性={list(det_periods)}, 鲁棒={list(rob_periods)}")
else:
    differences.append("OK: 需求列名一致")

cap_missing_det = [wh for wh in all_wh if wh not in cap_det]
if cap_missing_det:
    differences.append(f"BUG4: 确定性模型缺失容量: {cap_missing_det}")
else:
    differences.append("OK: 容量值完整")

differences.append("DIFF1: 确定性模型无距离过滤(>5000km), 鲁棒模型有")
differences.append("DIFF2: 确定性模型有CDC的y/z/w变量, 鲁棒模型没有")
differences.append("DIFF3: 确定性模型dist默认0, 鲁棒模型dist默认99999")

for d in differences:
    print(f"  {d}")
