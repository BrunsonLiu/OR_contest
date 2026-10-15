"""逐项对比确定性模型和鲁棒模型的目标函数计算方式"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np

BASE = str(_REPO_ROOT)

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

proc_cost = {}
cap = {}
open_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']

def loss_500(t):
    return 0.0 if t <= 500 else 0.2 * (t-500)**2 / 10000

def loss_600(t):
    return 0.0 if t <= 600 else 0.2 * (t-600)**2 / 10000

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)

demand = {}
for t_idx, dc in enumerate(forecast_dates):
    demand[t_idx] = {}
    for _, row in df_forecast.iterrows():
        demand[t_idx][(row['Customer'], row['SKU'])] = float(row[dc])

# 用鲁棒模型的解 (13 RDC) 计算成本
rob_rdcs = ['bei-jing-DC', 'chang-sha-DC', 'chong-qing-DC', 'da-lian-DC',
            'guang-zhou-DC', 'ha-er-bin-DC', 'nan-jing-DC', 'ning-bo-DC',
            'qing-dao-DC', 'tian-jin-DC', 'wu-han-DC', 'xi-an-DC', 'zheng-zhou-DC']

print("=" * 70)
print("关键检查: 损耗阈值 500 vs 600 对成本的影响")
print("=" * 70)

# 计算一个典型路线的损耗差异
for wh in rob_rdcs[:5]:
    for c in ['shang-hai-shi', 'hang-zhou-shi', 'dong-guan-shi']:
        d = dur.get((wh, c), None)
        if d:
            l500 = loss_500(d)
            l600 = loss_600(d)
            print(f"  {wh} → {c}: {d}min, loss(500)={l500:.4f}, loss(600)={l600:.4f}, 差={l500-l600:.4f}")

# 全量计算
print("\n" + "=" * 70)
print("全量: 损耗阈值500 vs 600 对总成本的影响")
print("=" * 70)

total_loss_500 = 0
total_loss_600 = 0
total_trans_cust = 0
total_trans_wh = 0
total_proc = 0

for t in range(T):
    for (c, sku), qty in demand[t].items():
        # 假设最优分配（选最近的RDC）
        eligible = [port_cdc] + rob_rdcs if sku == 'im' else [inland_cdc] + rob_rdcs
        best_wh = min(eligible, key=lambda w: dist.get((w, c), 99999))
        
        d = dist.get((best_wh, c), 0)
        t_min = dur.get((best_wh, c), 0)
        
        total_trans_cust += 1.45e-4 * d * qty
        total_loss_500 += loss_500(t_min) * qty
        total_loss_600 += loss_600(t_min) * qty
        total_proc += 2.0 * proc_cost.get(best_wh, 0) * qty

print(f"  运输(门): {total_trans_cust:.0f}")
print(f"  损耗(阈值500): {total_loss_500:.0f}")
print(f"  损耗(阈值600): {total_loss_600:.0f}")
print(f"  差异: {total_loss_500 - total_loss_600:.0f}")

# CDC→RDC段
total_loss_wh_500 = 0
total_loss_wh_600 = 0
total_trans_wh = 0
total_proc_wh = 0

for t in range(T):
    for rdc in rob_rdcs:
        for sku in ['im', 'dm']:
            cdc = port_cdc if sku == 'im' else inland_cdc
            # 估算调拨量 = 该RDC服务的门店需求之和
            rdc_qty = sum(qty for (c, s), qty in demand[t].items() if s == sku)
            # 简化：按比例分配
            rdc_qty_share = rdc_qty / len(rob_rdcs)
            
            d = dist.get((cdc, rdc), 0)
            t_min = dur.get((cdc, rdc), 0)
            
            total_trans_wh += 0.9e-4 * d * rdc_qty_share
            total_loss_wh_500 += loss_500(t_min) * rdc_qty_share
            total_loss_wh_600 += loss_600(t_min) * rdc_qty_share
            total_proc_wh += 2.0 * proc_cost.get(cdc, 0) * rdc_qty_share

print(f"\n  CDC→RDC段:")
print(f"  损耗(阈值500): {total_loss_wh_500:.0f}")
print(f"  损耗(阈值600): {total_loss_wh_600:.0f}")
print(f"  差异: {total_loss_wh_500 - total_loss_wh_600:.0f}")

print(f"\n  合计损耗(500): {total_loss_500 + total_loss_wh_500:.0f}")
print(f"  合计损耗(600): {total_loss_600 + total_loss_wh_600:.0f}")
print(f"  合计差异: {(total_loss_500 + total_loss_wh_500) - (total_loss_600 + total_loss_wh_600):.0f}")

# ========== 检查确定性模型的代码 ==========
print("\n" + "=" * 70)
print("检查确定性模型代码中的损耗公式")
print("=" * 70)

with open(f'{BASE}/src/solvers/question4/solve_problem4_loss.py', 'r', encoding='utf-8') as f:
    code = f.read()

import re
# 找 calculate_loss_cost 函数
match = re.search(r'def calculate_loss_cost.*?(?=\ndef |\Z)', code, re.DOTALL)
if match:
    func = match.group(0)
    print(f"  确定性模型的损耗函数:")
    for line in func.split('\n')[:10]:
        print(f"    {line}")
    
    if '600' in func:
        print(f"\n  🔴 确定性模型也用了 600 作为损耗阈值！")
    if '500' in func:
        print(f"  ✅ 确定性模型用了 500 作为损耗阈值")

# 检查鲁棒模型
with open(f'{BASE}/src/solvers/question4/solve_problem4_robust.py', 'r', encoding='utf-8') as f:
    code2 = f.read()

if 'LOSS_THRESHOLD = 500' in code2:
    print(f"\n  ✅ 鲁棒模型用了 LOSS_THRESHOLD = 500")
if 'TIMELINESS_THRESHOLD = 600' in code2:
    print(f"  ✅ 鲁棒模型时效阈值 = 600 (正确，与损耗无关)")

# ========== 检查处置费计算差异 ==========
print("\n" + "=" * 70)
print("检查处置费计算差异")
print("=" * 70)

# 确定性模型的处置费
# 从代码: proc_cost_val = 2.0 * proc_cost.get(wh, 0.0) * qty
# 鲁棒模型: 同样 2.0 * proc_cost * qty

# 但关键: 确定性模型中 u 变量的 obj 包含了处置费
# 鲁棒模型中 u 变量的 obj 也包含了处置费
# 但鲁棒模型的 K 系数计算方式不同

# 检查鲁棒模型的 K 系数
print("  鲁棒模型 K 系数计算:")
k_match = re.search(r'K_\{wh,c\}.*?=.*?(?=\n    for|\Z)', code2, re.DOTALL)
if k_match:
    print(f"    {k_match.group(0)[:200]}")

# ========== 检查智能系统折扣 ==========
print("\n" + "=" * 70)
print("检查智能系统折扣")
print("=" * 70)

# 确定性模型: w变量obj = 1.5 - 0.8*proc_cost
# 但折扣是怎么实现的？
# 搜索 w 变量的使用
w_lines = [l for l in code.split('\n') if 'w_' in l and ('var' in l or 'obj' in l) and 'write' not in l]
print(f"  确定性模型 w 变量相关行:")
for l in w_lines[:10]:
    print(f"    {l.strip()}")

# 鲁棒模型
w_lines2 = [l for l in code2.split('\n') if 'w_' in l and ('var' in l or 'obj' in l or 'coeff' in l) and 'write' not in l and '#' not in l]
print(f"\n  鲁棒模型 w 变量相关行:")
for l in w_lines2[:10]:
    print(f"    {l.strip()}")
