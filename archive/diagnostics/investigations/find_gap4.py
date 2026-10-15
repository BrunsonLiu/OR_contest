"""
终极对比: 从鲁棒模型的CPLEX解中提取u变量，看路由分配
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import cplex
import pandas as pd
import numpy as np
import json

BASE = str(_REPO_ROOT)

# 直接从鲁棒模型的CPLEX解中读取
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json', 'r', encoding='utf-8') as f:
    rob = json.load(f)

r0 = rob[0]
daily = r0['daily_costs']

df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
dur = {}
for _, r in df_matrix.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

# 从鲁棒模型结果中提取每天的路由
print("=" * 70)
print("鲁棒模型 Γ=0%: 每天的路由和损耗")
print("=" * 70)

for d in daily:
    day = d['day']
    routes = d.get('routes', [])
    if not routes:
        # 从 daily_costs 的其他字段推算
        print(f"  Day {day}: 无routes数据")
        continue
    
    day_loss = 0
    day_trans = 0
    for rt in routes:
        wh = rt['warehouse']
        c = rt['customer']
        s = rt['sku']
        qty = rt['qty']
        t_min = dur.get((wh, c), dur.get((c, wh), 0))
        loss = loss_per_ton(t_min) * qty
        day_loss += loss
    print(f"  Day {day}: routes={len(routes)}, loss={day_loss:.0f}, reported_loss={d.get('loss',0):.0f}")

# 检查: 鲁棒模型是否也允许CDC直接服务门店
print("\n" + "=" * 70)
print("检查: 鲁棒模型中CDC是否直接服务门店")
print("=" * 70)

cdc_direct = 0
rdc_serve = 0
for d in daily:
    routes = d.get('routes', [])
    for rt in routes:
        wh = rt['warehouse']
        if 'CDC' in wh:
            cdc_direct += rt['qty']
        else:
            rdc_serve += rt['qty']

print(f"  CDC直送: {cdc_direct:.0f} 吨")
print(f"  RDC配送: {rdc_serve:.0f} 吨")

# 关键问题: 鲁棒模型的u变量是否包含CDC?
# 如果不包含，那CDC→门店的损耗就不在u变量里
# 而是通过f变量(CDC→RDC)间接计算

# 让我直接检查鲁棒模型代码中u变量的创建范围
with open(f'{BASE}/src/solvers/question4/solve_problem4_robust.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 搜索 u 变量创建的循环范围
import re
u_creation = re.findall(r'for wh in (.*?)[:\n].*?u_.*?var', code)
print(f"\n  u变量的wh范围: {u_creation[:5]}")

# 检查 all_wh_names 的定义
all_wh_def = re.search(r"all_wh_names\s*=\s*(.*?)\n", code)
if all_wh_def:
    print(f"  all_wh_names = {all_wh_def.group(1)}")

# 检查鲁棒模型中CDC是否在u变量的候选列表中
if 'all_wh_names' in code:
    # all_wh_names = cdc_names + rdc_names
    print(f"  → CDC 在 u 变量候选列表中！")
    print(f"  → 鲁棒模型允许 CDC 直接服务门店")
else:
    print(f"  → CDC 不在 u 变量候选列表中")

# 最终检查: 鲁棒模型的损耗计算方式
print("\n" + "=" * 70)
print("鲁棒模型损耗计算方式")
print("=" * 70)

# 搜索损耗计算代码
loss_calc = [l for l in code.split('\n') if 'loss_t' in l or 'loss_cost' in l and 'calculate' not in l and '#' not in l]
for l in loss_calc[:15]:
    print(f"  {l.strip()}")

# 检查: 鲁棒模型是否在u变量的obj中包含了损耗?
u_obj_lines = [l for l in code.split('\n') if 'obj_val' in l and ('trans_cost' in l or 'loss' in l)]
print(f"\n  u变量obj计算:")
for l in u_obj_lines[:5]:
    print(f"    {l.strip()}")
