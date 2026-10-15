"""对比约束数量"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import cplex, pandas as pd, numpy as np

BASE = str(_REPO_ROOT)
df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_customer = pd.read_csv(f'{BASE}/data/raw/df_customer.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

dist = {}; dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

proc_cost = {}; cap = {}; open_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']
    cap[row['Name']] = row['Capacity']
    open_cost[row['Name']] = row['Opening_fee']

def loss_per_ton(m):
    return 0.0 if m <= 500 else 0.2*(m-500)**2/10000

cdc_names = df_wh[df_wh['Type']=='CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type']=='RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
customer_cities = list(df_customer['Name'])
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
skus = ['im', 'dm']
all_wh = cdc_names + rdc_names

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer','SKU']]
T = len(forecast_dates)

demand = {}
for t, dc in enumerate(forecast_dates):
    demand[t] = {}
    for _, row in df_forecast.iterrows():
        demand[t][(row['Customer'], row['SKU'])] = float(row[dc])

# 读取鲁棒模型代码，统计约束数量
with open(f'{BASE}/src/solvers/question4/solve_problem4_robust.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 搜索鲁棒模型中的约束计数
import re
constraint_counts = re.findall(r'add_constraint\(|linear_constraints\.add\(', code)
print(f"鲁棒模型 add_constraint 调用次数: {len(constraint_counts)}")

# 更精确: 搜索约束编号
constraint_labels = re.findall(r"# ---- \((\d+)\)", code)
print(f"鲁棒模型约束组: {constraint_labels}")

# 现在让我直接读鲁棒模型代码中的约束部分
# 找到所有约束组
constraint_sections = re.findall(r'# ---- \((\d+)\) (.*?) ----', code)
print(f"\n鲁棒模型约束组:")
for num, desc in constraint_sections:
    print(f"  ({num}) {desc}")

# 我需要检查鲁棒模型有哪些约束是我的find_bug.py没有的
# 让我直接读鲁棒模型的约束代码
print("\n" + "=" * 70)
print("检查: 鲁棒模型有哪些约束是 find_bug.py 可能缺少的")
print("=" * 70)

# 鲁棒模型约束列表 (从代码中提取):
# (1) 单源 Σu=1
# (2) u ≤ y (RDC only)
# (3) 开仓关系 open_new = y - y_prev
# (4) 仅开不关 y_t ≥ y_{t-1}
# (5) 流量平衡
# (6) RDC容量 (合并im+dm)
# (7) RDC容量辅助 (Gamma>0 only)
# (8) CDC容量 (预计算最坏需求)
# (9) 时效 v约束
# (10) 时效总约束
# (11) 智能系统 z约束
# (12) 智能系统 w ≤ 出库量

# 我的 find_bug.py 有:
# 1. 单源 ✅
# 2. u ≤ y ✅
# 3. 流量平衡 ✅
# 4. 容量 ✅
# 5. 时效 ✅
# 6. 仅开不关 ✅
# 7. open_new ✅
# 8. z约束 ✅

# 缺少:
# - CDC容量约束 ❌❌❌

print("  ❌ 缺少: CDC容量约束!")
print("  这意味着CDC可以无限量出货，CPLEX会让CDC直接服务所有门店")
print("  CDC→门店的损耗极高，但如果没有容量限制，CPLEX会选最便宜的路线")

# 让我加上CDC容量约束重新跑
print("\n" + "=" * 70)
print("加上CDC容量约束后重新求解")
print("=" * 70)

# CDC容量约束: Σ f_{cdc,rdc,s} + Σ u_{cdc,c,s}*qty ≤ cap_cdc
# 但鲁棒模型的CDC约束更复杂，让我先看代码
cdc_constraint_code = re.search(
    r'# ---- \(8\).*?(?=# ---- \(\d+\)|# ========)', code, re.DOTALL
)
if cdc_constraint_code:
    lines = cdc_constraint_code.group(0).split('\n')[:30]
    for l in lines:
        print(f"  {l}")
