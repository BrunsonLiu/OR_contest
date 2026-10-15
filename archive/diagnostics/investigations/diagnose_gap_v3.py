# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, json, os
import cplex
import numpy as np

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(INPUT, 'df_forecast.csv'))

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customers = df_customer['Name'].tolist()

dist_matrix = {}
for _, r in df_matrix.iterrows():
    dist_matrix[(r['From'], r['To'])] = r['Distance']
    dist_matrix[(r['To'], r['From'])] = r['Distance']

# ========== 1. 检查u变量空间差异 ==========
# 确定性模型: 无dist过滤
# 鲁棒模型: dist > 5000km 过滤

det_u_count = 0
rob_u_count = 0
filtered_routes = []

for c in customers:
    for s in ['im', 'dm']:
        eligible_det = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        eligible_rob = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        for wh in eligible_det:
            det_u_count += 1
            d = dist_matrix.get((wh, c), 99999)
            if d <= 5000:
                rob_u_count += 1
            else:
                filtered_routes.append((wh, c, s, d))

print(f'=== u变量空间对比 ===')
print(f'  确定性模型u变量数(每期): {det_u_count}')
print(f'  鲁棒模型u变量数(每期): {rob_u_count}')
print(f'  被过滤的路线数: {len(filtered_routes)}')
if filtered_routes:
    for wh, c, s, d in filtered_routes[:10]:
        print(f'    {wh} -> {c} ({s}): {d:.0f}km')

# ========== 2. 检查f变量空间差异 ==========
det_f_count = 0
rob_f_count = 0
filtered_f = []

for cdc in cdc_names:
    s = 'im' if cdc == port_cdc else 'dm'
    for rdc in rdc_names:
        det_f_count += 1
        d = dist_matrix.get((cdc, rdc), 99999)
        if d <= 5000:
            rob_f_count += 1
        else:
            filtered_f.append((cdc, rdc, s, d))

print(f'\n=== f变量空间对比 ===')
print(f'  确定性模型f变量数(每期): {det_f_count}')
print(f'  鲁棒模型f变量数(每期): {rob_f_count}')
print(f'  被过滤的路线数: {len(filtered_f)}')

# ========== 3. 检查需求覆盖差异 ==========
# 确定性模型: demand_multi[t] keys
# 鲁棒模型: demand_nominal[t] keys
# 需要构建两个demand字典

T = 7
demand_multi = {}
demand_nominal = {}

for day in range(T):
    date_str = f'2016-06-{24+day}'
    df_day = df_forecast[df_forecast['Date'] == date_str]
    demand_multi[day] = {}
    demand_nominal[day] = {}
    for _, row in df_day.iterrows():
        store = row['Customer']
        sku = row['SKU']
        qty = row['Forecast']
        demand_multi[day][(store, sku)] = qty
        demand_nominal[day][(store, sku)] = qty

det_demand_keys = set(demand_multi[0].keys())
rob_demand_keys = set(demand_nominal[0].keys())
print(f'\n=== 需求覆盖对比 ===')
print(f'  确定性模型需求keys: {len(det_demand_keys)}')
print(f'  鲁棒模型需求keys: {len(rob_demand_keys)}')
print(f'  差异: {det_demand_keys - rob_demand_keys}')

# ========== 4. 检查单源约束差异 ==========
# 确定性模型: Σ u = 1 for all (store, sku)
# 鲁棒模型: Σ u = 1 for all (c, s) where u variables exist

# 如果某些u变量被过滤，单源约束可能不完整
print(f'\n=== 单源约束差异 ===')
for c in customers:
    for s in ['im', 'dm']:
        eligible_det = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        eligible_rob = []
        for wh in eligible_det:
            d = dist_matrix.get((wh, c), 99999)
            if d <= 5000:
                eligible_rob.append(wh)
        if len(eligible_det) != len(eligible_rob):
            print(f'  {c}({s}): det={len(eligible_det)} whs, rob={len(eligible_rob)} whs')
            for wh in eligible_det:
                if wh not in eligible_rob:
                    d = dist_matrix.get((wh, c), 99999)
                    print(f'    被过滤: {wh}, dist={d:.0f}km')

# ========== 5. 检查CDC直送差异 ==========
print(f'\n=== CDC直送路径检查 ===')
for cdc in cdc_names:
    s = 'im' if cdc == port_cdc else 'dm'
    for c in customers:
        d = dist_matrix.get((cdc, c), 99999)
        if d > 5000:
            print(f'  {cdc} -> {c} ({s}): {d:.0f}km (鲁棒模型中无此u变量)')

# ========== 6. 检查损耗成本差异的具体来源 ==========
# 读取两个模型的路由，找出哪些路线的损耗不同
det_dir = os.path.join(BASE, 'results/question4', 'problem4_loss_v2', 'output_result')

# 构建确定性模型的路由字典
det_routing = {}
for day in range(T):
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
        if to not in rdc_names and to not in cdc_names:
            det_routing[(day, to, sku)] = (wh, qty)

# 鲁棒模型没有保存路由到CSV，需要从CPLEX解中提取
# 但我们可以从成本差异推断
print(f'\n=== 确定性模型路由统计 ===')
cdc_direct_count = 0
rdc_service_count = 0
for (day, c, s), (wh, qty) in det_routing.items():
    if wh in cdc_names:
        cdc_direct_count += 1
    else:
        rdc_service_count += 1
print(f'  CDC直送: {cdc_direct_count} 条路线')
print(f'  RDC配送: {rdc_service_count} 条路线')

# ========== 7. 检查处置成本计算差异 ==========
print(f'\n=== 处置成本计算差异 ===')
proc_cost_dict = {}
for _, row in pd.read_csv(os.path.join(INPUT, 'df_proc.csv')).iterrows():
    proc_cost_dict[row['Name']] = row['Processing_fee']

# 确定性模型: u变量中 2.0*proc_cost*qty, w变量中 -0.8*proc_cost
# 鲁棒模型: u变量中 2.0*proc_cost*qty, w变量中 -0.8*proc_cost
# 差异: 确定性模型有CDC的w变量, 鲁棒模型没有

cdc_proc_total = 0
for (day, c, s), (wh, qty) in det_routing.items():
    if wh in cdc_names:
        cdc_proc_total += 2.0 * proc_cost_dict.get(wh, 0) * qty

print(f'  确定性模型CDC处置成本(未折扣): {cdc_proc_total:.2f}')
print(f'  如果CDC采购智能系统, 折扣: {0.8 * cdc_proc_total / 2.0:.2f}')
print(f'  鲁棒模型无CDC智能系统, 无折扣')

# ========== 8. 检查确定性模型是否真的有19个仓库 ==========
print(f'\n=== 确定性模型开仓检查 ===')
det_open_rdcs = set()
for day in range(T):
    date_str = f'2016-06-{24+day}'
    fname = os.path.join(det_dir, f'仓网供应关系文件_{date_str}.csv')
    if not os.path.exists(fname):
        continue
    df = pd.read_csv(fname, encoding='utf-8-sig')
    for _, row in df.iterrows():
        wh = row.iloc[0]
        if wh in rdc_names:
            det_open_rdcs.add(wh)
print(f'  从供应关系推断的RDC: {len(det_open_rdcs)}个')
print(f'  RDC列表: {sorted(det_open_rdcs)}')

# 检查是否有RDC开了但没服务任何门店
all_rdcs_in_supply = set()
for day in range(T):
    date_str = f'2016-06-{24+day}'
    fname = os.path.join(det_dir, f'仓网供应关系文件_{date_str}.csv')
    if not os.path.exists(fname):
        continue
    df = pd.read_csv(fname, encoding='utf-8-sig')
    for _, row in df.iterrows():
        wh = row.iloc[0]
        to = row.iloc[1]
        if wh in rdc_names and to not in rdc_names and to not in cdc_names:
            all_rdcs_in_supply.add(wh)
print(f'  有门店配送的RDC: {len(all_rdcs_in_supply)}个')
print(f'  有门店配送的RDC列表: {sorted(all_rdcs_in_supply)}')

# 检查调拨关系中的RDC
transfer_rdcs = set()
for day in range(T):
    date_str = f'2016-06-{24+day}'
    fname = os.path.join(det_dir, f'仓网供应关系文件_{date_str}.csv')
    if not os.path.exists(fname):
        continue
    df = pd.read_csv(fname, encoding='utf-8-sig')
    for _, row in df.iterrows():
        wh = row.iloc[0]
        to = row.iloc[1]
        if wh in cdc_names and to in rdc_names:
            transfer_rdcs.add(to)
print(f'  接收调拨的RDC: {len(transfer_rdcs)}个')
print(f'  接收调拨的RDC列表: {sorted(transfer_rdcs)}')
