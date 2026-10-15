# -*- coding: utf-8 -*-
"""
计算确定性模型中CDC→RDC调拨段的损耗成本
并与鲁棒模型对比
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

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

time_mat = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    time_mat[(o, d)] = row['Duration']
    time_mat[(d, o)] = row['Duration']

dist_mat = {}
for _, row in df_matrix.iterrows():
    o, d = row['From'], row['To']
    dist_mat[(o, d)] = row['Distance']
    dist_mat[(d, o)] = row['Distance']

LOSS_THRESHOLD = 500.0
def calc_loss(minutes):
    if minutes <= LOSS_THRESHOLD:
        return 0.0
    return 0.2 * (minutes - LOSS_THRESHOLD) ** 2 / 10000.0

cap = {}
proc_cost_wh = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost_wh[row['Name']] = row['Processing_fee']

# ========== 1. 确定性模型: CDC→RDC调拨损耗 ==========
print("=" * 70)
print("确定性模型: CDC→RDC调拨损耗分析")
print("=" * 70)

det_dir = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result')
periods_det = ['2016-06-24', '2016-06-25', '2016-06-26', '2016-06-27', '2016-06-28', '2016-06-29', '2016-06-30']

total_transfer_loss = 0
total_transfer_transport = 0
total_transfer_proc = 0
transfer_by_route = {}

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
        
        if wh in cdc_names and cust in rdc_names:
            tt = time_mat.get((wh, cust), 10000)
            dist_val = dist_mat.get((wh, cust), 0)
            loss = calc_loss(tt) * qty
            transport = 0.9e-4 * dist_val * qty
            proc = 2.0 * proc_cost_wh.get(wh, 0) * qty
            
            total_transfer_loss += loss
            total_transfer_transport += transport
            total_transfer_proc += proc
            
            key = (wh, cust, sku)
            if key not in transfer_by_route:
                transfer_by_route[key] = {'qty': 0, 'loss': 0, 'transport': 0, 'tt': tt}
            transfer_by_route[key]['qty'] += qty
            transfer_by_route[key]['loss'] += loss
            transfer_by_route[key]['transport'] += transport

print(f"  CDC→RDC总调拨量: {sum(v['qty'] for v in transfer_by_route.values()):.2f}吨")
print(f"  CDC→RDC总损耗: {total_transfer_loss:.2f}万元")
print(f"  CDC→RDC总运输: {total_transfer_transport:.2f}万元")
print(f"  CDC→RDC总处置: {total_transfer_proc:.2f}万元")

# 按损耗排序
print(f"\n  CDC→RDC高损耗调拨路线(前15):")
sorted_routes = sorted(transfer_by_route.items(), key=lambda x: -x[1]['loss'])
for (wh, rdc, sku), info in sorted_routes[:15]:
    print(f"    {wh}→{rdc}({sku}): qty={info['qty']:.2f}吨, time={info['tt']:.0f}min, loss={info['loss']:.2f}万, transport={info['transport']:.2f}万")

# ========== 2. 按CDC分组 ==========
print(f"\n  按CDC分组:")
for cdc in cdc_names:
    cdc_loss = sum(v['loss'] for k, v in transfer_by_route.items() if k[0] == cdc)
    cdc_qty = sum(v['qty'] for k, v in transfer_by_route.items() if k[0] == cdc)
    cdc_transport = sum(v['transport'] for k, v in transfer_by_route.items() if k[0] == cdc)
    print(f"    {cdc}: qty={cdc_qty:.2f}吨, loss={cdc_loss:.2f}万, transport={cdc_transport:.2f}万")

# ========== 3. 按RDC分组 ==========
print(f"\n  按RDC分组(调拨入库):")
rdc_transfer = {}
for rdc in rdc_names:
    rdc_loss = sum(v['loss'] for k, v in transfer_by_route.items() if k[1] == rdc)
    rdc_qty = sum(v['qty'] for k, v in transfer_by_route.items() if k[1] == rdc)
    rdc_transfer[rdc] = {'qty': rdc_qty, 'loss': rdc_loss}

for rdc in sorted(rdc_transfer.keys(), key=lambda x: -rdc_transfer[x]['loss']):
    info = rdc_transfer[rdc]
    if info['qty'] > 0:
        print(f"    {rdc}: qty={info['qty']:.2f}吨, loss={info['loss']:.2f}万")

# ========== 4. 关键对比：gang-kou-CDC→各RDC的im调拨 ==========
print(f"\n" + "=" * 70)
print("gang-kou-CDC→RDC im调拨损耗 (确定性模型)")
print("=" * 70)

port_routes = {k: v for k, v in transfer_by_route.items() if k[0] == port_cdc}
for (wh, rdc, sku), info in sorted(port_routes.items(), key=lambda x: -x[1]['loss']):
    print(f"  {wh}→{rdc}({sku}): qty={info['qty']:.2f}吨, time={info['tt']:.0f}min, loss={info['loss']:.2f}万")

# ========== 5. 检查gang-kou-CDC→ning-bo-DC的异常 ==========
print(f"\n" + "=" * 70)
print("关键异常: gang-kou-CDC→ning-bo-DC im调拨")
print("=" * 70)

tt_gk_nb = time_mat.get((port_cdc, 'ning-bo-DC'), 10000)
dist_gk_nb = dist_mat.get((port_cdc, 'ning-bo-DC'), 0)
print(f"  运输时间: {tt_gk_nb:.0f}min")
print(f"  运输距离: {dist_gk_nb:.0f}km")
print(f"  损耗率: {calc_loss(tt_gk_nb):.6f}万/吨")
print(f"  损耗阈值: {LOSS_THRESHOLD}min")

# 检查所有CDC→RDC的运输时间
print(f"\n  所有CDC→RDC运输时间:")
for cdc in cdc_names:
    for rdc in rdc_names:
        tt = time_mat.get((cdc, rdc), 99999)
        dist_val = dist_mat.get((cdc, rdc), 0)
        loss_rate = calc_loss(tt)
        if loss_rate > 0:
            print(f"    {cdc}→{rdc}: time={tt:.0f}min, dist={dist_val:.0f}km, loss_rate={loss_rate:.6f}万/吨")

# ========== 6. 对比鲁棒模型 ==========
print(f"\n" + "=" * 70)
print("鲁棒模型Gamma=0%: 成本分解对比")
print("=" * 70)

robust_result_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust', 'robust_results.json')
if os.path.exists(robust_result_file):
    with open(robust_result_file, 'r', encoding='utf-8') as f:
        robust_results = json.load(f)
    gamma0 = robust_results[0]
    
    det_total = 233949.68
    rob_total = gamma0.get('total_cost', 0)
    
    print(f"  确定性总成本: {det_total:.2f}万")
    print(f"  鲁棒G=0%总成本: {rob_total:.2f}万")
    print(f"  差异: {det_total - rob_total:.2f}万 ({(det_total - rob_total)/rob_total*100:.2f}%)")
    
    print(f"\n  成本分解对比:")
    print(f"  {'项目':<15} {'确定性':>12} {'鲁棒G=0%':>12} {'差异':>12}")
    print(f"  {'-'*55}")
    
    det_loss = 219875.88
    det_proc = 1321.26
    det_trans_cust = 5715.02
    det_trans_wh = 6612.01
    det_open = 400.0
    det_smart = 25.5
    
    rob_loss = gamma0.get('loss_cost', 0)
    rob_proc = gamma0.get('proc_cost_actual', 0)
    rob_trans_cust = gamma0.get('transport_cost_customer', 0)
    rob_trans_wh = gamma0.get('transport_cost_warehouse', 0)
    rob_open = gamma0.get('open_cost', 0)
    rob_smart = gamma0.get('smart_cost', 0)
    
    for name, d, r in [('损耗', det_loss, rob_loss), ('处置', det_proc, rob_proc),
                        ('运输(门店)', det_trans_cust, rob_trans_cust), ('运输(仓库)', det_trans_wh, rob_trans_wh),
                        ('开仓', det_open, rob_open), ('智能系统', det_smart, rob_smart)]:
        print(f"  {name:<15} {d:>12.2f} {r:>12.2f} {d-r:>12.2f}")

# ========== 7. 关键洞察：确定性模型的CDC直接服务是否导致更多远距离调拨 ==========
print(f"\n" + "=" * 70)
print("关键洞察: CDC直接服务→RDC调拨量变化→损耗变化")
print("=" * 70)

# 如果CDC不直接服务门店，所有需求都通过RDC，调拨量会增加
# 但近距RDC的调拨损耗低，远距RDC的调拨损耗不变
# 所以总调拨损耗应该降低

# 计算CDC直接服务节省的调拨损耗
cdc_direct_qty_by_rdc = {}
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
            # CDC直接服务门店
            # 如果改为通过最近的RDC服务，需要CDC→RDC调拨
            cdc = wh
            best_rdc = None
            best_tt = 10000
            for rdc in rdc_names:
                rdc_tt = time_mat.get((rdc, cust), 10000)
                if rdc_tt < best_tt:
                    best_tt = rdc_tt
                    best_rdc = rdc
            
            if best_rdc:
                cdc_rdc_tt = time_mat.get((cdc, best_rdc), 10000)
                additional_transfer_loss = calc_loss(cdc_rdc_tt) * qty
                
                if best_rdc not in cdc_direct_qty_by_rdc:
                    cdc_direct_qty_by_rdc[best_rdc] = {'qty': 0, 'additional_loss': 0}
                cdc_direct_qty_by_rdc[best_rdc]['qty'] += qty
                cdc_direct_qty_by_rdc[best_rdc]['additional_loss'] += additional_transfer_loss

total_additional_loss = sum(v['additional_loss'] for v in cdc_direct_qty_by_rdc.values())
total_cdc_direct_qty = sum(v['qty'] for v in cdc_direct_qty_by_rdc.values())

print(f"  CDC直接服务总量: {total_cdc_direct_qty:.2f}吨")
print(f"  如果改为RDC服务，额外调拨损耗: {total_additional_loss:.2f}万")
print(f"  → CDC直接服务节省调拨损耗: {total_additional_loss:.2f}万")
print(f"  → 但确定性模型总损耗反而更高!")

print(f"\n  这说明问题不在CDC直接服务，而在RDC→门店路由!")
print(f"  确定性模型的RDC选择了更远的门店服务路线")

# ========== 8. 检查RDC→门店路由差异 ==========
print(f"\n" + "=" * 70)
print("RDC→门店路由损耗分析(确定性模型)")
print("=" * 70)

rdc_to_store_loss = {}
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
        
        if wh in rdc_names and cust not in rdc_names and cust not in cdc_names:
            tt = time_mat.get((wh, cust), 10000)
            loss = calc_loss(tt) * qty
            key = (wh, cust, sku)
            if key not in rdc_to_store_loss:
                rdc_to_store_loss[key] = {'qty': 0, 'loss': 0, 'tt': tt}
            rdc_to_store_loss[key]['qty'] += qty
            rdc_to_store_loss[key]['loss'] += loss

# 找出高损耗的RDC→门店路线
print(f"  高损耗RDC→门店路线(前20):")
sorted_rdc_store = sorted(rdc_to_store_loss.items(), key=lambda x: -x[1]['loss'])
for (wh, cust, sku), info in sorted_rdc_store[:20]:
    # 检查是否有更近的RDC
    best_rdc = None
    best_tt = 10000
    for rdc in rdc_names:
        rdc_tt = time_mat.get((rdc, cust), 10000)
        if rdc_tt < best_tt:
            best_tt = rdc_tt
            best_rdc = rdc
    print(f"    {wh}→{cust}({sku}): qty={info['qty']:.2f}, time={info['tt']:.0f}min, loss={info['loss']:.2f}万, 最近RDC={best_rdc}({best_tt:.0f}min)")
