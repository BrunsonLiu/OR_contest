"""
最终核心对比：检查鲁棒模型是否使用CDC直接服务，以及两个模型的详细差异
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import json
import numpy as np

# 数据加载
df_wh = pd.read_csv('data/raw/df_wh.csv')
df_matrix = pd.read_csv('data/raw/df_matrix.csv')
df_proc = pd.read_csv('data/raw/df_proc.csv')
df_customer = pd.read_csv('data/raw/df_customer.csv')
df_forecast = pd.read_csv('results/question3/订单需求量预测结果文件_sota.csv')

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
all_wh = cdc_names + rdc_names
customers = df_customer['Name'].tolist()

port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

# 构建距离矩阵
dist_bidir = {}
dur_bidir = {}
for _, row in df_matrix.iterrows():
    dist_bidir[(row['From'], row['To'])] = row['Distance']
    dist_bidir[(row['To'], row['From'])] = row['Distance']
    dur_bidir[(row['From'], row['To'])] = row['Duration']
    dur_bidir[(row['To'], row['From'])] = row['Duration']

dist_oneway = {(row['From'], row['To']): row['Distance'] for _, row in df_matrix.iterrows()}
dur_oneway = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}

proc_cost = {}
cap = {}
open_cost_dict = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']
    cap[row['Name']] = row['Capacity']
    open_cost_dict[row['Name']] = row['Opening_fee']

def calc_loss(minutes, threshold=500):
    if minutes <= threshold:
        return 0.0
    return 0.2 * (minutes - threshold) ** 2 / 10000.0

# 需求数据
periods = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(periods)
demand = {}
for t, p in enumerate(periods):
    demand[t] = {}
    for _, row in df_forecast.iterrows():
        demand[t][(row['Customer'], row['SKU'])] = float(row[p])

# ========== 1. 确定性模型中CDC直接服务的详细成本分析 ==========
print("=" * 80)
print("1. 确定性模型中CDC直接服务的详细成本分析")
print("=" * 80)

periods_str = ['2016-06-24', '2016-06-25', '2016-06-26', '2016-06-27',
               '2016-06-28', '2016-06-29', '2016-06-30']

cdc_direct_total = 0
cdc_direct_trans = 0
cdc_direct_loss = 0
cdc_direct_proc = 0

for t, p in enumerate(periods_str):
    df_supply = pd.read_csv(f'results/question4/problem4_loss_v2/output_result/仓网供应关系文件_{p}.csv')
    cdc_direct = df_supply[df_supply['仓库名称'].isin(cdc_names) & ~df_supply['服务对象'].str.contains('DC')]

    for _, row in cdc_direct.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        qty = row['数量（吨）']
        d = dist_oneway.get((wh, cust), 0)
        dur = dur_oneway.get((wh, cust), 0)
        cdc_direct_total += qty
        cdc_direct_trans += 1.45e-4 * d * qty
        cdc_direct_loss += calc_loss(dur) * qty
        cdc_direct_proc += 2.0 * proc_cost.get(wh, 0) * qty

print(f'  CDC直接服务总量(7天): {cdc_direct_total:.2f}吨')
print(f'  CDC直接服务运输成本: {cdc_direct_trans:.2f}万')
print(f'  CDC直接服务损耗成本: {cdc_direct_loss:.2f}万')
print(f'  CDC直接服务处置成本: {cdc_direct_proc:.2f}万')
print(f'  CDC直接服务总成本: {cdc_direct_trans + cdc_direct_loss + cdc_direct_proc:.2f}万')

# ========== 2. 如果CDC直接服务改由RDC服务，成本是多少？ ==========
print()
print("=" * 80)
print("2. CDC直接服务客户改由RDC服务的替代成本估算")
print("=" * 80)

# 对于CDC直接服务的每个客户，找最近的RDC，计算RDC服务成本
rdc_alternative_total = 0
rdc_alternative_trans = 0
rdc_alternative_loss = 0
rdc_alternative_proc = 0
rdc_alternative_transfer = 0

for t, p in enumerate(periods_str):
    df_supply = pd.read_csv(f'results/question4/problem4_loss_v2/output_result/仓网供应关系文件_{p}.csv')
    cdc_direct = df_supply[df_supply['仓库名称'].isin(cdc_names) & ~df_supply['服务对象'].str.contains('DC')]

    for _, row in cdc_direct.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']

        # 找到成本最低的RDC（运输+损耗+处置+调拨）
        best_cost = float('inf')
        best_rdc = None
        for rdc in rdc_names:
            d_rdc = dist_oneway.get((rdc, cust), 0)
            dur_rdc = dur_oneway.get((rdc, cust), 0)
            d_cdc_rdc = dist_oneway.get((wh, rdc), 0)
            dur_cdc_rdc = dur_oneway.get((wh, rdc), 0)

            trans = 1.45e-4 * d_rdc * qty + 0.9e-4 * d_cdc_rdc * qty
            loss = calc_loss(dur_rdc) * qty + calc_loss(dur_cdc_rdc) * qty
            proc = 2.0 * proc_cost.get(rdc, 0) * qty + 2.0 * proc_cost.get(wh, 0) * qty
            total = trans + loss + proc

            if total < best_cost:
                best_cost = total
                best_rdc = rdc

        if best_rdc:
            d_rdc = dist_oneway.get((best_rdc, cust), 0)
            dur_rdc = dur_oneway.get((best_rdc, cust), 0)
            d_cdc_rdc = dist_oneway.get((wh, best_rdc), 0)
            dur_cdc_rdc = dur_oneway.get((wh, best_rdc), 0)

            rdc_alternative_total += qty
            rdc_alternative_trans += 1.45e-4 * d_rdc * qty
            rdc_alternative_loss += calc_loss(dur_rdc) * qty
            rdc_alternative_proc += 2.0 * proc_cost.get(best_rdc, 0) * qty
            rdc_alternative_transfer += 0.9e-4 * d_cdc_rdc * qty + calc_loss(dur_cdc_rdc) * qty + 2.0 * proc_cost.get(wh, 0) * qty

print(f'  RDC替代方案总量(7天): {rdc_alternative_total:.2f}吨')
print(f'  RDC->客户运输成本: {rdc_alternative_trans:.2f}万')
print(f'  RDC->客户损耗成本: {rdc_alternative_loss:.2f}万')
print(f'  RDC->客户处置成本: {rdc_alternative_proc:.2f}万')
print(f'  CDC->RDC调拨成本: {rdc_alternative_transfer:.2f}万')
print(f'  RDC替代总成本: {rdc_alternative_trans + rdc_alternative_loss + rdc_alternative_proc + rdc_alternative_transfer:.2f}万')
print(f'  成本差异(CDC直接 - RDC替代): {(cdc_direct_trans + cdc_direct_loss + cdc_direct_proc) - (rdc_alternative_trans + rdc_alternative_loss + rdc_alternative_proc + rdc_alternative_transfer):.2f}万')

# ========== 3. 检查确定性模型中CDC直接服务是否节省了CDC->RDC调拨 ==========
print()
print("=" * 80)
print("3. CDC直接服务对CDC->RDC调拨的影响")
print("=" * 80)

# 确定性模型中CDC调拨量
det_transfer_total = 0
for t, p in enumerate(periods_str):
    df_supply = pd.read_csv(f'results/question4/problem4_loss_v2/output_result/仓网供应关系文件_{p}.csv')
    cdc_transfer = df_supply[df_supply['仓库名称'].isin(cdc_names) & df_supply['服务对象'].str.contains('DC')]
    det_transfer_total += cdc_transfer['数量（吨）'].sum()

print(f'  确定性模型CDC->RDC调拨总量(7天): {det_transfer_total:.2f}吨')
print(f'  确定性模型CDC直接服务总量(7天): {cdc_direct_total:.2f}吨')
print(f'  如果CDC不直接服务，调拨量将增加: {cdc_direct_total:.2f}吨')

# ========== 4. 检查CDC容量是否是瓶颈 ==========
print()
print("=" * 80)
print("4. CDC容量分析")
print("=" * 80)

for cdc in cdc_names:
    cdc_cap = cap.get(cdc, 0)
    print(f'  {cdc}: 容量={cdc_cap}吨/天')
    for t, p in enumerate(periods_str[:1]):
        df_supply = pd.read_csv(f'results/question4/problem4_loss_v2/output_result/仓网供应关系文件_{p}.csv')
        cdc_rows = df_supply[df_supply['仓库名称'] == cdc]
        total_throughput = cdc_rows['数量（吨）'].sum()
        direct_service = cdc_rows[~cdc_rows['服务对象'].str.contains('DC')]['数量（吨）'].sum()
        transfer = cdc_rows[cdc_rows['服务对象'].str.contains('DC')]['数量（吨）'].sum()
        print(f'    Day{t}: 总吞吐={total_throughput:.2f}, 直接服务={direct_service:.2f}, 调拨={transfer:.2f}, 利用率={total_throughput/cdc_cap*100:.1f}%')

# ========== 5. 核心问题：确定性模型中0距离路线对u变量目标系数的影响 ==========
print()
print("=" * 80)
print("5. 确定性模型中CDC直接服务的u变量目标系数分析")
print("=" * 80)

# 在确定性模型中，CDC->客户的u变量目标系数 = trans + loss + proc
# 其中trans和loss基于dist.get((wh,store),0)和loss_cost_matrix.get((wh,store),0)
# 对于CDC直接服务的客户，这些值是正确的（非0）
# 但对于距离矩阵中缺失的路线，dist=0, time=0, trans=0, loss=0

# 检查确定性模型中所有u变量的目标系数
print('  确定性模型CDC直接服务客户的u变量系数:')
for t, p in enumerate(periods_str[:1]):
    df_supply = pd.read_csv(f'results/question4/problem4_loss_v2/output_result/仓网供应关系文件_{p}.csv')
    cdc_direct = df_supply[df_supply['仓库名称'].isin(cdc_names) & ~df_supply['服务对象'].str.contains('DC')]

    for _, row in cdc_direct.iterrows():
        wh = row['仓库名称']
        cust = row['服务对象']
        sku = row['商品类型']
        qty = row['数量（吨）']

        d = dist_oneway.get((wh, cust), 0)
        dur = dur_oneway.get((wh, cust), 0)
        trans = 1.45e-4 * d * qty
        loss = calc_loss(dur) * qty
        proc = 2.0 * proc_cost.get(wh, 0) * qty
        total = trans + loss + proc

        # 同一客户由RDC服务的成本
        best_rdc_cost = float('inf')
        for rdc in rdc_names:
            d_rdc = dist_oneway.get((rdc, cust), 0)
            dur_rdc = dur_oneway.get((rdc, cust), 0)
            d_cdc_rdc = dist_oneway.get((wh, rdc), 0)
            dur_cdc_rdc = dur_oneway.get((wh, rdc), 0)
            rdc_total = (1.45e-4 * d_rdc * qty + calc_loss(dur_rdc) * qty + 2.0 * proc_cost.get(rdc, 0) * qty +
                        0.9e-4 * d_cdc_rdc * qty + calc_loss(dur_cdc_rdc) * qty + 2.0 * proc_cost.get(wh, 0) * qty)
            if rdc_total < best_rdc_cost:
                best_rdc_cost = rdc_total

        if total > best_rdc_cost:
            print(f'  !! {wh}->{cust}({sku}): CDC成本={total:.2f} > 最佳RDC成本={best_rdc_cost:.2f}, 差={total-best_rdc_cost:.2f}')

# ========== 6. 检查鲁棒模型中CDC u变量是否存在 ==========
print()
print("=" * 80)
print("6. 鲁棒模型中CDC u变量存在性检查")
print("=" * 80)

# 鲁棒模型中，CDC在eligible_whs中，但距离过滤可能排除某些路线
# 检查CDC->客户的距离是否都<=5000
for cdc in cdc_names:
    s = 'im' if cdc == port_cdc else 'dm'
    far_customers = 0
    for c in customers:
        if (c, s) not in demand[0]:
            continue
        d = dist_bidir.get((cdc, c), 99999)
        if d > 5000:
            far_customers += 1
            print(f'  {cdc}->{c}({s}): dist={d} > 5000, 被过滤!')
    if far_customers == 0:
        print(f'  {cdc}: 所有{ s }客户路线距离都<=5000km, CDC u变量都会被创建')

# ========== 7. 关键差异汇总：两个模型的完整差异列表 ==========
print()
print("=" * 80)
print("7. 两个模型完整差异汇总")
print("=" * 80)

print('''
A. 变量差异:
  1. 确定性模型有CDC的y变量(lb=1,始终为1), 鲁棒模型没有CDC的y变量
  2. 确定性模型有CDC的z变量(智能系统采购), 鲁棒模型没有CDC的z变量
  3. 确定性模型有CDC的w变量(折扣量), 鲁棒模型没有CDC的w变量
  4. 确定性模型有CDC的open_new变量, 鲁棒模型没有(但CDC也不需要,因为必开)

B. 约束差异:
  1. 确定性模型有CDC的u<=y约束, 鲁棒模型没有(但CDC始终开放,效果相同)
  2. 确定性模型有CDC的z<=sum(y)约束, 鲁棒模型没有(因为无CDC z变量)
  3. 确定性模型有CDC的w约束(w<=总出库, w<=z*cap), 鲁棒模型没有(因为无CDC w变量)
  4. 时效约束:
     - 确定性模型: time<=600时v>=u, time>600时v+u<=1
     - 鲁棒模型: v<=sum(u(wh where time<=600))
     效果: 确定性模型强制v=1当服务在时效内, 鲁棒模型允许v=0即使服务在时效内

C. 目标函数差异:
  1. 确定性模型CDC可以有智能系统折扣(-0.8*proc_cost[cdc]*w), 鲁棒模型没有
  2. 两个模型的u/f变量系数计算公式相同(已验证)

D. 距离矩阵差异:
  1. 确定性模型使用单向矩阵(dist.get(key,0)), 鲁棒模型使用双向矩阵(dist_matrix.get(key,99999))
  2. 但所有WH->Cust和CDC->RDC路线在两个矩阵中值相同(已验证)
  3. tai-zhou-shi不在距离矩阵中,但也不在需求数据中,不影响结果

E. 开设仓库:
  1. 两个模型开设完全相同的16个RDC
  2. 确定性模型额外使用CDC直接服务34个客户/天
''')

# ========== 8. 最终结论 ==========
print("=" * 80)
print("8. 最终结论：成本差异的根本原因")
print("=" * 80)

total_demand = sum(sum(demand[t].values()) for t in range(T))
print(f'  总需求(7天): {total_demand:.2f}吨')
print(f'  CDC直接服务占比: {cdc_direct_total/total_demand*100:.1f}%')
print()
print('  成本差异分解:')
det_loss = 219875.88
robust_loss = 210562.10
det_proc = 1321.26
robust_proc = 1798.95
det_trans_cust = 5715.02
robust_trans_cust = 5802.41
det_trans_wh = 6612.01
robust_trans_wh = 6536.60
det_smart = 25.5
robust_smart = 22.5

print(f'  损耗成本差异: {det_loss - robust_loss:.2f}万 (确定性更高)')
print(f'  处置成本差异: {det_proc - robust_proc:.2f}万 (确定性更低,因CDC折扣)')
print(f'  门店运输差异: {det_trans_cust - robust_trans_cust:.2f}万 (确定性更低)')
print(f'  仓间运输差异: {det_trans_wh - robust_trans_wh:.2f}万 (确定性更高)')
print(f'  智能系统差异: {det_smart - robust_smart:.2f}万 (确定性更高)')
print(f'  总差异: {233949.68 - 225122.56:.2f}万')
print()
print('  根本原因分析:')
print('  1. [主因] 损耗成本差异9,313万是总差异的主要来源')
print('  2. [关键] 两个模型开设相同的16个RDC,但客户分配不同')
print('  3. [机制] 确定性模型使用CDC直接服务,改变了流量平衡,')
print('     可能导致RDC的客户分配次优,增加了损耗成本')
print('  4. [验证] CDC直接服务本身损耗很低(7天约61万),')
print('     但它改变了CDC->RDC调拨量,间接影响了RDC的客户分配')
print('  5. [补充] 鲁棒模型缺少CDC的z/w变量,CDC无法获得折扣,')
print('     这使得CDC直接服务在鲁棒模型中相对更贵,')
print('     优化器倾向于不使用CDC直接服务,反而找到了更优的RDC分配方案')
