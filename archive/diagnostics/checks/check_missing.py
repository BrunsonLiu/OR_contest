"""检查40个缺失的dist/dur对"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd

BASE = str(_REPO_ROOT)
df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_customer = pd.read_csv(f'{BASE}/data/raw/df_customer.csv')

dist = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
all_wh = cdc_names + rdc_names
customer_cities = list(df_customer['Name'])

print("缺失的 dist 对:")
for wh in all_wh:
    for c in customer_cities:
        if (wh, c) not in dist:
            print(f"  {wh} → {c}")

# 检查: 鲁棒模型是否对这些对使用了默认值
# 如果鲁棒模型用 dist=99999 过滤 (d_km > 5000 → skip)
# 那这些对不会创建u变量 → 正确

# 但如果鲁棒模型用 dist=0 默认值
# 那这些对会创建u变量，obj=0 → CPLEX会优先选这些路线！

print(f"\n缺失对总数: {sum(1 for wh in all_wh for c in customer_cities if (wh,c) not in dist)}")

# 检查鲁棒模型的代码
with open(f'{BASE}/src/solvers/question4/solve_problem4_robust.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 搜索 u 变量创建时的 dist 过滤
import re
u_create = [l.strip() for l in code.split('\n') if 'dist_km' in l or 'dist_matrix.get' in l and 'u_' in l]
print("\n鲁棒模型 u 变量创建时的 dist 过滤:")
for l in u_create[:10]:
    print(f"  {l}")

# 搜索 f 变量创建时的 dist 过滤
f_create = [l.strip() for l in code.split('\n') if 'dist_km' in l and 'f_' in l]
print("\n鲁棒模型 f 变量创建时的 dist 过滤:")
for l in f_create[:10]:
    print(f"  {l}")
