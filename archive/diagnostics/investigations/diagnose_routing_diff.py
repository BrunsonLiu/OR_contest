# -*- coding: utf-8 -*-
"""
深入诊断：对比确定性模型 vs 鲁棒模型的路由差异
重点：CDC直接服务门店 vs RDC服务门店的损耗差异
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

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

dist = {}
time_mat = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist[(o, d)] = row['Distance']
    dist[(d, o)] = row['Distance']
    time_mat[(o, d)] = row['Duration']
    time_mat[(d, o)] = row['Duration']

LOSS_THRESHOLD = 500.0
def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

cap = {}
proc_cost_wh = {}
open_cost_wh = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost_wh[row['Name']] = row['Processing_fee']
    open_cost_wh[row['Name']] = row['Opening_fee']

# ========== 1. 容量数据 ==========
print("=" * 70)
print("RDC容量数据")
print("=" * 70)
for wh in rdc_names:
    c = cap.get(wh, 0)
    pc = proc_cost_wh.get(wh, 0)
    oc = open_cost_wh.get(wh, 0)
    print(f"  {wh}: cap={c}, proc={pc}, open={oc}")

print(f"\nCDC容量数据:")
for wh in cdc_names:
    c = cap.get(wh, 0)
    pc = proc_cost_wh.get(wh, 0)
    print(f"  {wh}: cap={c}, proc={pc}")

# ========== 2. 读取确定性模型的供应关系 ==========
print("\n" + "=" * 70)
print("确定性模型: CDC直接服务门店 vs RDC服务门店")
print("=" * 70)

det_dir = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result')
periods_det = ['2016-06-24', '2016-06-25', '2016-06-26', '2016-06-27', '2016-06-28', '2016-06-29', '2016-06-30']

cdc_direct_loss = 0
cdc_direct_qty = 0
rdc_service_loss = 0
rdc_service_qty = 0
cdc_direct_routes = []

for period in periods_det:
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_sup = pd.read_csv(fname, encoding='utf-8-sig')
    
    for _, row in df_sup.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if wh in cdc_names and cust not in rdc_names and cust not in cdc_names:
            tt = time_mat.get((wh, cust), 10000)
            loss = calc_loss(tt) * qty
            cdc_direct_loss += loss
            cdc_direct_qty += qty
            if loss > 100:
                cdc_direct_routes.append((wh, cust, sku, qty, tt, loss))
        elif wh in rdc_names:
            tt = time_mat.get((wh, cust), 10000)
            loss = calc_loss(tt) * qty
            rdc_service_loss += loss
            rdc_service_qty += qty

print(f"  CDC直接服务门店: qty={cdc_direct_qty:.2f}吨, loss={cdc_direct_loss:.2f}万元")
print(f"  RDC服务门店: qty={rdc_service_qty:.2f}吨, loss={rdc_service_loss:.2f}万元")
print(f"  CDC直接服务平均损耗: {cdc_direct_loss/cdc_direct_qty*10000:.2f}元/吨" if cdc_direct_qty > 0 else "  N/A")
print(f"  RDC服务平均损耗: {rdc_service_loss/rdc_service_qty*10000:.2f}元/吨" if rdc_service_qty > 0 else "  N/A")

print(f"\n  CDC直接服务高损耗路线(>100万):")
cdc_direct_routes.sort(key=lambda x: -x[5])
for wh, cust, sku, qty, tt, loss in cdc_direct_routes[:20]:
    print(f"    {wh}→{cust}({sku}): qty={qty:.2f}, time={tt:.0f}min, loss={loss:.2f}万")

# ========== 3. 检查CDC直接服务的路线是否有更优RDC替代 ==========
print("\n" + "=" * 70)
print("CDC直接服务路线的RDC替代方案分析")
print("=" * 70)

for wh, cust, sku, qty, tt, loss in cdc_direct_routes[:10]:
    print(f"\n  {wh}→{cust}({sku}): 当前损耗={loss:.2f}万, 运输时间={tt:.0f}min")
    eligible_rdcs = rdc_names
    alternatives = []
    for rdc in eligible_rdcs:
        rdc_tt = time_mat.get((rdc, cust), 10000)
        rdc_loss = calc_loss(rdc_tt) * qty
        cdc_to_rdc_tt = time_mat.get((wh, rdc), 10000)
        cdc_to_rdc_loss = calc_loss(cdc_to_rdc_tt) * qty
        total_rdc_loss = rdc_loss + cdc_to_rdc_loss
        alternatives.append((rdc, rdc_tt, rdc_loss, cdc_to_rdc_tt, cdc_to_rdc_loss, total_rdc_loss))
    
    alternatives.sort(key=lambda x: x[5])
    for rdc, rdc_tt, rdc_loss, cdc_rdc_tt, cdc_rdc_loss, total in alternatives[:3]:
        saving = loss - total
        print(f"    替代: {rdc}→{cust}({rdc_tt:.0f}min, loss={rdc_loss:.2f}) + {wh}→{rdc}({cdc_rdc_tt:.0f}min, loss={cdc_rdc_loss:.2f}) = {total:.2f}万 (省{saving:.2f}万)")

# ========== 4. 检查确定性模型中各RDC的容量使用率 ==========
print("\n" + "=" * 70)
print("确定性模型: RDC容量使用率")
print("=" * 70)

for period in periods_det:
    fname = os.path.join(det_dir, f'仓网供应关系文件_{period}.csv')
    if not os.path.exists(fname):
        continue
    df_sup = pd.read_csv(fname, encoding='utf-8-sig')
    
    if period != periods_det[0]:
        continue
    
    rdc_usage = {}
    for _, row in df_sup.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']
        
        if wh in rdc_names and cust not in rdc_names and cust not in cdc_names:
            if wh not in rdc_usage:
                rdc_usage[wh] = 0
            rdc_usage[wh] += qty
    
    for wh in rdc_names:
        used = rdc_usage.get(wh, 0)
        c = cap.get(wh, 0)
        pct = used / c * 100 if c > 0 else 0
        print(f"  {wh}: used={used:.2f}/{c}, 使用率={pct:.1f}%")

# ========== 5. 检查nei-lu-CDC直接服务的关键路线 ==========
print("\n" + "=" * 70)
print("关键问题: nei-lu-CDC→bei-jing-shi(dm) 为什么不走bei-jing-DC?")
print("=" * 70)

# 检查bei-jing-DC的容量
bj_cap = cap.get('bei-jing-DC', 0)
print(f"  bei-jing-DC容量: {bj_cap}")

# 检查bei-jing-DC在确定性模型中服务了哪些城市
fname = os.path.join(det_dir, f'仓网供应关系文件_{periods_det[0]}.csv')
df_sup = pd.read_csv(fname, encoding='utf-8-sig')
bj_service = df_sup[(df_sup['仓库名称'] == 'bei-jing-DC') & (~df_sup['服务对象'].isin(rdc_names + cdc_names))]
print(f"  bei-jing-DC直接服务的门店:")
bj_total = 0
for _, row in bj_service.iterrows():
    print(f"    →{row['服务对象']}({row['商品类型']}): {row['数量（吨）']:.2f}吨")
    bj_total += row['数量（吨）']
print(f"  bei-jing-DC总服务量: {bj_total:.2f}吨")
print(f"  bei-jing-DC剩余容量: {bj_cap - bj_total:.2f}吨")

# 检查nei-lu-CDC直接服务的dm需求
nei_lu_direct = df_sup[(df_sup['仓库名称'] == 'nei-lu-CDC') & (~df_sup['服务对象'].isin(rdc_names + cdc_names)) & (df_sup['商品类型'] == 'dm')]
nei_lu_total = nei_lu_direct['数量（吨）'].sum()
print(f"\n  nei-lu-CDC直接服务dm总量: {nei_lu_total:.2f}吨")

# 检查这些需求如果转给bei-jing-DC会怎样
print(f"\n  nei-lu-CDC直接服务dm路线(按损耗排序):")
nei_lu_direct_list = []
for _, row in nei_lu_direct.iterrows():
    cust = row['服务对象']
    qty = row['数量（吨）']
    tt = time_mat.get(('nei-lu-CDC', cust), 10000)
    loss = calc_loss(tt) * qty
    bj_tt = time_mat.get(('bei-jing-DC', cust), 10000)
    bj_loss = calc_loss(bj_tt) * qty
    nei_lu_direct_list.append((cust, qty, tt, loss, bj_tt, bj_loss))

nei_lu_direct_list.sort(key=lambda x: -x[3])
for cust, qty, tt, loss, bj_tt, bj_loss in nei_lu_direct_list[:15]:
    saving = loss - bj_loss
    print(f"    →{cust}: qty={qty:.2f}, CDC_time={tt:.0f}min(loss={loss:.2f}), BJ_time={bj_tt:.0f}min(loss={bj_loss:.2f}), 省{saving:.2f}万")

# ========== 6. 检查CDC的容量使用率 ==========
print("\n" + "=" * 70)
print("CDC容量使用率(第一天)")
print("=" * 70)

for cdc in cdc_names:
    cdc_service = df_sup[(df_sup['仓库名称'] == cdc)]
    cdc_direct = cdc_service[~cdc_service['服务对象'].isin(rdc_names + cdc_names)]
    cdc_transfer = cdc_service[cdc_service['服务对象'].isin(rdc_names)]
    
    direct_qty = cdc_direct['数量（吨）'].sum()
    transfer_qty = cdc_transfer['数量（吨）'].sum()
    total_qty = direct_qty + transfer_qty
    c = cap.get(cdc, 0)
    
    print(f"  {cdc}:")
    print(f"    直接服务门店: {direct_qty:.2f}吨")
    print(f"    调拨到RDC: {transfer_qty:.2f}吨")
    print(f"    总出库: {total_qty:.2f}吨")
    print(f"    容量: {c}, 使用率: {total_qty/c*100:.1f}%" if c > 0 else "    容量: 0")

# ========== 7. 关键发现：容量约束是否过紧 ==========
print("\n" + "=" * 70)
print("关键分析: 容量约束是否阻止了更优路由?")
print("=" * 70)

# 计算如果所有CDC直接服务的dm需求都转给最近的RDC，RDC容量是否够
print("  假设: 将nei-lu-CDC直接服务的dm需求全转给RDC")
rdc_additional = {}
for cust, qty, tt, loss, bj_tt, bj_loss in nei_lu_direct_list:
    # 找最近的RDC
    best_rdc = None
    best_tt = 10000
    for rdc in rdc_names:
        rdc_tt = time_mat.get((rdc, cust), 10000)
        if rdc_tt < best_tt:
            best_tt = rdc_tt
            best_rdc = rdc
    if best_rdc:
        if best_rdc not in rdc_additional:
            rdc_additional[best_rdc] = 0
        rdc_additional[best_rdc] += qty

print(f"  各RDC需要额外承载的dm需求:")
for rdc in sorted(rdc_additional.keys()):
    add_qty = rdc_additional[rdc]
    # 当前使用量
    rdc_service = df_sup[(df_sup['仓库名称'] == rdc) & (~df_sup['服务对象'].isin(rdc_names + cdc_names))]
    cur_qty = rdc_service['数量（吨）'].sum()
    c = cap.get(rdc, 0)
    new_total = cur_qty + add_qty
    print(f"    {rdc}: 当前={cur_qty:.2f}, 新增={add_qty:.2f}, 总计={new_total:.2f}/{c} ({new_total/c*100:.1f}%) {'***超出容量!' if new_total > c else ''}")
