# -*- coding: utf-8 -*-
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import sys, io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd, json, os

BASE = str(_REPO_ROOT)
INPUT = os.path.join(BASE, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT, 'df_matrix.csv'))
df_proc = pd.read_csv(os.path.join(INPUT, 'df_proc.csv'))
df_customer = pd.read_csv(os.path.join(INPUT, 'df_customer.csv'))
df_order = pd.read_csv(os.path.join(INPUT, 'df_order.csv'))

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customers = df_customer['Name'].tolist()

dist_matrix = {}
dur_matrix = {}
for _, r in df_matrix.iterrows():
    dist_matrix[(r['From'], r['To'])] = r['Distance']
    dist_matrix[(r['To'], r['From'])] = r['Distance']
    dur_matrix[(r['From'], r['To'])] = r['Duration']
    dur_matrix[(r['To'], r['From'])] = r['Duration']

# 1. 检查dist > 5000km过滤的影响
print('=== dist > 5000km 过滤影响 ===')
filtered_u = []
for c in customers:
    for s in ['im', 'dm']:
        eligible = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            d = dist_matrix.get((wh, c), 99999)
            if d > 5000:
                filtered_u.append((wh, c, s, d))

print(f'  被过滤的u变量: {len(filtered_u)}')
for wh, c, s, d in filtered_u:
    print(f'    {wh} -> {c} ({s}): {d:.0f}km')

# 2. 检查确定性模型中这些路线的obj系数
if filtered_u:
    print(f'\n  确定性模型中这些路线的obj系数:')
    for wh, c, s, d in filtered_u:
        qty_im = df_order[(df_order['Name']==c) & (df_order['SKU']=='im')]['qty'].values
        qty_dm = df_order[(df_order['Name']==c) & (df_order['SKU']=='dm')]['qty'].values
        qty = qty_im[0] if s == 'im' and len(qty_im) > 0 else (qty_dm[0] if s == 'dm' and len(qty_dm) > 0 else 0)
        trans_cost = 1.45e-4 * d * qty
        print(f'    {wh} -> {c} ({s}): dist={d:.0f}km, qty={qty:.1f}, trans_cost={trans_cost:.2f}')

# 3. 检查f变量过滤
print(f'\n=== f变量过滤 ===')
filtered_f = []
for cdc in cdc_names:
    s = 'im' if cdc == port_cdc else 'dm'
    for rdc in rdc_names:
        d = dist_matrix.get((cdc, rdc), 99999)
        if d > 5000:
            filtered_f.append((cdc, rdc, s, d))
print(f'  被过滤的f变量: {len(filtered_f)}')

# 4. 检查单源约束完整性
print(f'\n=== 单源约束完整性 ===')
incomplete_sources = []
for c in customers:
    for s in ['im', 'dm']:
        eligible_det = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        eligible_rob = [wh for wh in eligible_det if dist_matrix.get((wh, c), 99999) <= 5000]
        if len(eligible_rob) == 0:
            incomplete_sources.append((c, s))
            print(f'  警告: {c}({s}) 在鲁棒模型中无可用仓库!')
        elif len(eligible_rob) < len(eligible_det):
            missing = [wh for wh in eligible_det if wh not in eligible_rob]
            if len(missing) > 0:
                print(f'  {c}({s}): det={len(eligible_det)} whs, rob={len(eligible_rob)} whs, missing={[w for w in missing]}')

# 5. 对比两个模型的u变量数量
det_u_count = 0
rob_u_count = 0
for c in customers:
    for s in ['im', 'dm']:
        eligible = [port_cdc] + rdc_names if s == 'im' else [inland_cdc] + rdc_names
        for wh in eligible:
            det_u_count += 1
            if dist_matrix.get((wh, c), 99999) <= 5000:
                rob_u_count += 1

print(f'\n  确定性模型u变量数(每期): {det_u_count}')
print(f'  鲁棒模型u变量数(每期): {rob_u_count}')
print(f'  差异: {det_u_count - rob_u_count}')

# 6. 关键检查: 确定性模型中CDC直送门店的损耗
print(f'\n=== CDC直送门店损耗分析 ===')
def calc_loss(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

for cdc in cdc_names:
    s = 'im' if cdc == port_cdc else 'dm'
    print(f'\n  {cdc} ({s}):')
    high_loss_customers = []
    for c in customers:
        d = dist_matrix.get((cdc, c), 99999)
        t = dur_matrix.get((cdc, c), 99999)
        loss = calc_loss(t)
        if d > 5000 or loss > 50:
            qty_row = df_order[(df_order['Name']==c) & (df_order['SKU']==s)]
            qty = qty_row['qty'].values[0] if len(qty_row) > 0 else 0
            high_loss_customers.append((c, d, t, loss, qty))
    high_loss_customers.sort(key=lambda x: -x[3])
    for c, d, t, loss, qty in high_loss_customers[:10]:
        print(f'    {c}: dist={d:.0f}km, time={t:.0f}min, loss/ton={loss:.2f}万, qty={qty:.1f}吨, total_loss={loss*qty:.2f}万')

# 7. 检查确定性模型中CDC是否直送了高损耗门店
det_dir = os.path.join(BASE, 'results/question4', 'problem4_loss_v2', 'output_result')
print(f'\n=== 确定性模型CDC直送分析 ===')
for day in range(1):
    fname = os.path.join(det_dir, f'仓网供应关系文件_2016-06-24.csv')
    if not os.path.exists(fname):
        continue
    df = pd.read_csv(fname, encoding='utf-8-sig')
    cdc_direct_loss = 0
    cdc_direct_count = 0
    cdc_direct_details = []
    for _, row in df.iterrows():
        wh = row.iloc[0]
        to = row.iloc[1]
        sku = row.iloc[2]
        qty = float(row.iloc[3])
        if wh in cdc_names and to not in rdc_names:
            t = dur_matrix.get((wh, to), 99999)
            loss = calc_loss(t)
            total_loss = loss * qty
            cdc_direct_loss += total_loss
            cdc_direct_count += 1
            if total_loss > 5:
                cdc_direct_details.append((wh, to, sku, qty, t, loss, total_loss))
    print(f'  CDC直送路线数: {cdc_direct_count}')
    print(f'  CDC直送损耗: {cdc_direct_loss:.2f}万')
    cdc_direct_details.sort(key=lambda x: -x[6])
    for wh, to, sku, qty, t, loss, total_loss in cdc_direct_details[:10]:
        d = dist_matrix.get((wh, to), 0)
        print(f'    {wh} -> {to} ({sku}): qty={qty:.1f}, dist={d:.0f}km, time={t:.0f}min, loss/ton={loss:.2f}, total={total_loss:.2f}')

# 8. 检查确定性模型中CDC->RDC调拨的损耗
print(f'\n=== CDC->RDC调拨损耗分析(第一天) ===')
fname = os.path.join(det_dir, f'仓网供应关系文件_2016-06-24.csv')
df = pd.read_csv(fname, encoding='utf-8-sig')
transfer_loss = 0
transfer_details = []
for _, row in df.iterrows():
    wh = row.iloc[0]
    to = row.iloc[1]
    sku = row.iloc[2]
    qty = float(row.iloc[3])
    if wh in cdc_names and to in rdc_names:
        t = dur_matrix.get((wh, to), 99999)
        loss = calc_loss(t)
        total_loss = loss * qty
        transfer_loss += total_loss
        transfer_details.append((wh, to, sku, qty, t, loss, total_loss))
print(f'  CDC->RDC调拨损耗: {transfer_loss:.2f}万')
transfer_details.sort(key=lambda x: -x[6])
for wh, to, sku, qty, t, loss, total_loss in transfer_details[:15]:
    d = dist_matrix.get((wh, to), 0)
    print(f'    {wh} -> {to} ({sku}): qty={qty:.1f}, dist={d:.0f}km, time={t:.0f}min, loss/ton={loss:.2f}, total={total_loss:.2f}')

# 9. 检查鲁棒模型中CDC直送门店的情况
print(f'\n=== 鲁棒模型CDC直送门店分析 ===')
with open(os.path.join(BASE, 'results/question4', 'problem4_robust', 'robust_results.json'), 'r', encoding='utf-8') as f:
    rob = json.load(f)
r0 = rob[0]
print(f'  鲁棒模型损耗: {r0["loss_cost"]:.2f}万')
print(f'  确定性模型损耗: 219875.52万 (从供应关系重建)')
print(f'  差异: {219875.52 - r0["loss_cost"]:.2f}万')

# 10. 检查确定性模型中处置成本的w折扣
print(f'\n=== 确定性模型w折扣分析 ===')
# 确定性模型中w的obj是 -0.8 * proc_cost[wh]
# 对于CDC, w折扣可以减少处置成本
for cdc in cdc_names:
    print(f'  {cdc}: proc_cost={df_proc[df_proc["Name"]==cdc]["Processing_fee"].values[0]:.2f}, w折扣/吨=0.8*{df_proc[df_proc["Name"]==cdc]["Processing_fee"].values[0]:.2f}={0.8*df_proc[df_proc["Name"]==cdc]["Processing_fee"].values[0]:.2f}')
