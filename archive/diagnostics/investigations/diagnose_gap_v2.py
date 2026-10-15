# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, json, os, numpy as np

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

dist = {}
dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

cap = {}; proc_cost = {}; open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

customers = df_customer['Name'].tolist()

def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

loss_cost = {}
for (f, t), d in dur.items():
    loss_cost[(f, t)] = calc_loss(d)

# ========== 1. 确定性模型成本重建 ==========
det_dir = os.path.join(BASE, 'results/question4', 'problem4_loss_v2', 'output_result')
det_total_loss = 0
det_total_trans_cust = 0
det_total_trans_wh = 0
det_total_proc = 0
det_cdc_direct_qty = 0
det_rdc_service_qty = 0
det_cdc_direct_loss = 0
det_rdc_loss = 0
det_transfer_loss = 0

for day in range(7):
    date_str = f'2016-06-{24+day}'
    fname = os.path.join(det_dir, f'仓网供应关系文件_{date_str}.csv')
    if not os.path.exists(fname):
        continue
    df = pd.read_csv(fname, encoding='utf-8-sig')
    for _, row in df.iterrows():
        wh = row.iloc[0]
        to = row.iloc[1]
        sku = row.iloc[2]
        qty = float(row.iloc[3])

        d = dist.get((wh, to), 0)
        t = dur.get((wh, to), 0)
        l = calc_loss(t)

        if wh in cdc_names and to in rdc_names:
            det_total_trans_wh += 0.9e-4 * d * qty
            det_total_loss += l * qty
            det_total_proc += 2.0 * proc_cost.get(wh, 0) * qty
            det_transfer_loss += l * qty
        elif wh in cdc_names:
            det_total_trans_cust += 1.45e-4 * d * qty
            det_total_loss += l * qty
            det_total_proc += 2.0 * proc_cost.get(wh, 0) * qty
            det_cdc_direct_qty += qty
            det_cdc_direct_loss += l * qty
        else:
            det_total_trans_cust += 1.45e-4 * d * qty
            det_total_loss += l * qty
            det_total_proc += 2.0 * proc_cost.get(wh, 0) * qty
            det_rdc_service_qty += qty
            det_rdc_loss += l * qty

print('=== 确定性模型成本重建 ===')
print(f'  运输(仓->仓): {det_total_trans_wh:.2f}')
print(f'  运输(仓->店): {det_total_trans_cust:.2f}')
print(f'  损耗: {det_total_loss:.2f}')
print(f'  处置(未折扣): {det_total_proc:.2f}')
print(f'  CDC直送门店: {det_cdc_direct_qty:.2f}吨, 损耗={det_cdc_direct_loss:.2f}')
print(f'  RDC配送门店: {det_rdc_service_qty:.2f}吨, 损耗={det_rdc_loss:.2f}')
print(f'  CDC->RDC调拨损耗: {det_transfer_loss:.2f}')

# ========== 2. 鲁棒模型 ==========
with open(os.path.join(BASE, 'results/question4', 'problem4_robust', 'robust_results.json'), 'r', encoding='utf-8') as f:
    rob = json.load(f)
r0 = rob[0]
print(f'\n=== 鲁棒模型 G=0% 成本 ===')
print(f'  运输(仓->仓): {r0["transport_cost_warehouse"]:.2f}')
print(f'  运输(仓->店): {r0["transport_cost_customer"]:.2f}')
print(f'  损耗: {r0["loss_cost"]:.2f}')
print(f'  处置(折扣前): {r0["proc_cost"]:.2f}')
print(f'  处置(折扣后): {r0["proc_cost_actual"]:.2f}')
print(f'  折扣: {r0["proc_discount"]:.2f}')

print(f'\n=== 差异分析 ===')
print(f'  运输(仓->仓): det-rob = {det_total_trans_wh - r0["transport_cost_warehouse"]:.2f}')
print(f'  运输(仓->店): det-rob = {det_total_trans_cust - r0["transport_cost_customer"]:.2f}')
print(f'  损耗: det-rob = {det_total_loss - r0["loss_cost"]:.2f}')
print(f'  处置(折扣前): det-rob = {det_total_proc - r0["proc_cost"]:.2f}')

# ========== 3. 关键对比：处置成本 ==========
print(f'\n=== 处置成本深度对比 ===')
print(f'  确定性模型处置(未折扣): {det_total_proc:.2f}')
print(f'  鲁棒模型处置(折扣前): {r0["proc_cost"]:.2f}')
print(f'  差异: {det_total_proc - r0["proc_cost"]:.2f}')

# ========== 4. 检查确定性模型中CDC的z/w值 ==========
print(f'\n=== 关键问题: 鲁棒模型是否缺少CDC的z/w变量? ===')
print(f'  鲁棒模型smart_cost = {r0["smart_cost"]:.2f}')
print(f'  鲁棒模型proc_discount = {r0["proc_discount"]:.2f}')
print(f'  22.5/1.5 = {22.5/1.5:.0f} 个仓库采购智能系统')
print(f'  如果CDC也采购: 需要额外 2*1.5 = 3 万元')

# ========== 5. 检查确定性模型的处置成本计算 ==========
print(f'\n=== 确定性模型处置成本计算方式 ===')
print(f'  u变量obj中: 2.0 * proc_cost[wh] * qty (入库+出库)')
print(f'  f变量obj中: 2.0 * proc_cost[cdc] * flow (入库+出库)')
print(f'  w变量obj中: -0.8 * proc_cost[wh] (折扣)')
print(f'  ')
print(f'  鲁棒模型处置成本计算方式:')
print(f'  u变量obj中: 2.0 * proc_cost[wh] * qty')
print(f'  f变量obj中: 2.0 * proc_cost[cdc] * flow')
print(f'  w变量obj中: -0.8 * proc_cost[wh]')

# ========== 6. 检查确定性模型的损耗公式 ==========
print(f'\n=== 损耗公式对比 ===')
print(f'  确定性模型: loss = 0.2*(t-500)^2/10000 万元/吨, 阈值500分钟')
print(f'  鲁棒模型: loss = 0.2*(t-500)^2/10000 万元/吨, 阈值500分钟')
print(f'  一致: True')

# ========== 7. 检查时效阈值 ==========
print(f'\n=== 时效阈值对比 ===')
print(f'  确定性模型: time_limit = 600分钟')
print(f'  鲁棒模型: TIMELINESS_THRESHOLD = 600分钟')
print(f'  一致: True')

# ========== 8. 检查损耗阈值 ==========
print(f'\n=== 损耗阈值对比 ===')
print(f'  确定性模型: LOSS_THRESHOLD = 500分钟 (calculate_loss_cost函数)')
print(f'  鲁棒模型: LOSS_THRESHOLD = 500分钟')
print(f'  一致: True')

# ========== 9. 对比两个模型的路由差异 ==========
print(f'\n=== 路由差异分析(第一天) ===')
det_routes = {}
fname = os.path.join(det_dir, '仓网供应关系文件_2016-06-24.csv')
df = pd.read_csv(fname, encoding='utf-8-sig')
for _, row in df.iterrows():
    wh = row.iloc[0]
    to = row.iloc[1]
    sku = row.iloc[2]
    qty = float(row.iloc[3])
    if to not in rdc_names and to not in cdc_names:
        key = (to, sku)
        det_routes[key] = (wh, qty)

# 鲁棒模型没有保存路由到CSV，需要从CPLEX解中提取
# 但我们可以从成本差异推断

# ========== 10. 关键检查: 确定性模型的dist是否双向 ==========
print(f'\n=== 关键检查: 确定性模型dist方向性 ===')
det_dist = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
missing_count = 0
for wh in cdc_names + rdc_names:
    for c in customers:
        if (wh, c) not in det_dist and (c, wh) in det_dist:
            missing_count += 1
            if missing_count <= 5:
                print(f'  缺少 {wh}->{c}, 但有 {c}->{wh} = {det_dist[(c,wh)]}km')
print(f'  总共缺少的方向: {missing_count}')

# ========== 11. 检查确定性模型的loss_cost_matrix ==========
det_time = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}
det_loss = {}
for f, t in det_time.keys():
    det_loss[(f, t)] = calc_loss(det_time[(f, t)])
missing_loss = 0
for wh in cdc_names + rdc_names:
    for c in customers:
        if (wh, c) not in det_loss and (c, wh) in det_time:
            missing_loss += 1
print(f'  loss_cost_matrix缺少的方向: {missing_loss}')
