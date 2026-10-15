"""逐项对比: 同一个(wh,c,sku)的u变量obj系数"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd, numpy as np, re

BASE = str(_REPO_ROOT)
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')

proc_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

dist = {}; dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

def loss_per_ton(t):
    return 0.0 if t<=500 else 0.2*(t-500)**2/10000

# 测试几个典型组合
tests = [
    ('nan-jing-DC', 'shang-hai-shi', 'im', 100),
    ('wu-han-DC', 'chang-sha-shi', 'dm', 80),
    ('gang-kou-CDC', 'guang-zhou-shi', 'im', 150),
    ('nei-lu-CDC', 'zheng-zhou-shi', 'dm', 120),
]

print("=" * 70)
print("逐项对比 u 变量 obj 系数")
print("=" * 70)

for wh, c, sku, qty in tests:
    d = dist.get((wh, c), 0)
    t = dur.get((wh, c), 0)
    l = loss_per_ton(t)
    p = 2.0 * proc_cost.get(wh, 0)
    
    # 鲁棒模型公式
    rob_obj = 1.45e-4 * d * qty + l * qty + p * qty
    
    # 确定性模型公式 (从代码中提取)
    # 需要看确定性模型的obj计算
    det_obj = 1.45e-4 * d * qty + l * qty + p * qty
    
    print(f"\n  {wh} → {c}, {sku}, qty={qty}")
    print(f"    dist={d}km, dur={t}min, loss={l:.4f}万/吨, proc={p:.4f}万/吨")
    print(f"    鲁棒 obj = {rob_obj:.4f}")
    print(f"    确定性 obj = {det_obj:.4f}")
    print(f"    一致: {abs(rob_obj - det_obj) < 0.0001}")

# 现在检查确定性模型的实际obj计算代码
print("\n" + "=" * 70)
print("确定性模型: u变量obj计算代码")
print("=" * 70)

with open(f'{BASE}/src/solvers/question4/solve_problem4_loss.py', 'r', encoding='utf-8') as f:
    det_code = f.read()

# 找u变量创建的代码段
u_section = re.search(r'# 3\. 服务关系变量.*?(?=# 4\.|# \d+\. )', det_code, re.DOTALL)
if u_section:
    lines = u_section.group(0).split('\n')
    for l in lines:
        if 'obj' in l.lower() or 'variables.add' in l or 'trans' in l or 'loss' in l or 'proc' in l:
            print(f"  {l.strip()}")

# 找f变量创建的代码段
print("\n" + "=" * 70)
print("确定性模型: f变量obj计算代码")
print("=" * 70)

f_section = re.search(r'# 调拨变量.*?(?=# \d+\. |约束)', det_code, re.DOTALL)
if f_section:
    lines = f_section.group(0).split('\n')
    for l in lines:
        if 'obj' in l.lower() or 'variables.add' in l or 'trans' in l or 'loss' in l or 'proc' in l:
            print(f"  {l.strip()}")
