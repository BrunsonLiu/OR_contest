"""
精确对比: timeliness约束的差异
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import os
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = str(_REPO_ROOT)
INPUT_DIR = os.path.join(BASE_DIR, 'data/raw')

df_wh = pd.read_csv(os.path.join(INPUT_DIR, 'df_wh.csv'))
df_matrix = pd.read_csv(os.path.join(INPUT_DIR, 'df_matrix.csv'))
df_customer = pd.read_csv(os.path.join(INPUT_DIR, 'df_customer.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
all_wh_names = cdc_names + rdc_names
customer_cities = list(df_customer['Name'])
skus = ['im', 'dm']
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

# 时间矩阵
dur_matrix = {}
for _, row in df_matrix.iterrows():
    dur_matrix[(row['From'], row['To'])] = row['Duration']
    dur_matrix[(row['To'], row['From'])] = row['Duration']

TIMELINESS_THRESHOLD = 600

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

# ============================================
# 关键分析: timeliness约束的数学形式
# ============================================
print("=" * 70)
print("关键分析: timeliness约束的数学形式")
print("=" * 70)

print("""
确定性模型 (solve_problem4_loss.py line 377-409):
---------------------------------
对于每个周期t，每个(store, sku):

1. 对每个wh，如果wh在eligible_whs中:
   - 如果 travel_time(wh, store) <= 600:
     约束: v - u >= 0  (即 v >= u)
     含义: 如果wh服务store，则v必须=1
   
   - 如果 travel_time(wh, store) > 600:
     约束: v + u <= 1
     含义: 如果wh服务store，则v必须=0

2. 整体时效约束:
   Σ v * qty >= 0.95 * Σ demand


鲁棒模型 (solve_problem4_robust.py line 601-638):
---------------------------------
对于每个周期t，每个(c, s):

1. v约束:
   v <= Σ_{wh: time<=600} u
   含义: v不能超过快速仓库服务的量

2. 整体时效约束:
   Σ v * qty >= 0.95 * worst_total (Γ=0%时等于nominal)

""")

# ============================================
# 数学等价性验证
# ============================================
print("\n" + "=" * 70)
print("数学等价性验证")
print("=" * 70)

print("""
假设有一个需求(c,s)可以被3个仓库服务: wh1(快速), wh2(快速), wh3(慢速)
单源约束: u1 + u2 + u3 = 1

确定性模型约束:
- v >= u1 (来自wh1)
- v >= u2 (来自wh2)
- v <= 1 - u3 (来自wh3)

结合单源约束:
- 如果u1=1: v >= 1, v <= 0 → 矛盾?!
  不，如果u3=0，则v <= 1，所以v >= 1 → v = 1
- 如果u2=1: 同上，v = 1
- 如果u3=1: v >= 0, v <= 0 → v = 0

所以确定性模型强制:
- 如果被快速仓库服务，v = 1
- 如果被慢速仓库服务，v = 0


鲁棒模型约束:
- v <= u1 + u2 (只有快速仓库)

结合单源约束:
- 如果u1=1: v <= 1 → v可以是0或1
- 如果u2=1: v <= 1 → v可以是0或1
- 如果u3=1: v <= 0 → v = 0

关键差异:
- 确定性模型: v >= u_fast (强制v=1如果被快速仓库服务)
- 棒模型: v <= Σ u_fast (只限制v的上界)

这就是问题所在!
鲁棒模型的v约束只限制了上界，没有强制下界!
""")

# ============================================
# 具体例子: LP relaxation中的差异
# ============================================
print("\n" + "=" * 70)
print("具体例子: LP relaxation中的差异")
print("=" * 70)

print("""
在LP relaxation中，所有变量都是连续的(0到1之间):

确定性模型:
- v >= u_fast → v必须至少等于快速仓库的分配量
- 如果u_fast = 0.5，则v >= 0.5
- 这限制了v的下界

鲁棒模型:
- v <= Σ u_fast → v最多等于快速仓库的总分配量
- 如果Σ u_fast = 0.5，则v <= 0.5
- 这只限制了v的上界

关键问题:
在LP relaxation中，确定性模型强制v >= u_fast
而鲁棒模型只限制v <= Σ u_fast

这意味着在鲁棒模型的LP relaxation中:
- v可以取很小的值(接近0)，即使被快速仓库服务
- 这会导致时效约束更容易满足(因为v可以取最优值)
- 从而降低LP relaxation的目标值

这就是为什么鲁棒模型的LP relaxation更低!
""")

# ============================================
# 修复方案
# ============================================
print("\n" + "=" * 70)
print("修复方案")
print("=" * 70)

print("""
要让鲁棒模型Γ=0%与确定性模型等价，需要修改timeliness约束:

当前鲁棒模型约束:
v <= Σ_{wh: time<=600} u

需要添加:
v >= Σ_{wh: time<=600} u - Σ_{wh: time>600} u

或者更简单:
v >= u_fast (对每个快速仓库)

但这样会大大增加约束数量...

更好的方案:
保持鲁棒模型的约束形式，但添加:
v >= 1 - Σ_{wh: time>600} u

这等价于:
v >= Σ_{wh: time<=600} u (因为单源约束 Σ u = 1)

所以修复方案是:
1. v <= Σ u_fast (现有约束)
2. v >= Σ u_fast (新增约束)

这两个约束结合起来就是 v = Σ u_fast
这在整数解时与确定性模型等价!
""")

# ============================================
# 验证修复效果
# ============================================
print("\n" + "=" * 70)
print("验证: 添加v >= Σ u_fast约束的效果")
print("=" * 70)

# 计算如果添加v >= Σ u_fast约束，LP relaxation会如何变化
print("""
如果添加 v >= Σ u_fast 约束:

在LP relaxation中:
- v = Σ u_fast (因为同时有 v <= Σ u_fast 和 v >= Σ u_fast)
- 这与确定性模型的 v = max(u_fast) 在整数解时等价

预期效果:
- LP relaxation应该上升到与确定性模型相近的水平
- MIP解也应该更接近确定性模型

""")

# ============================================
# 检查代码实现
# ============================================
print("\n" + "=" * 70)
print("检查代码实现")
print("=" * 70)

# 读取鲁棒模型代码中的timeliness约束
with open(os.path.join(BASE_DIR, 'src/solvers/question4/solve_problem4_robust.py'), 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("\n鲁棒模型timeliness v约束代码 (line 601-622):")
for i in range(600, 625):
    if i < len(lines):
        print(f"  {i+1}: {lines[i]}", end='')

print("\n\n确定性模型timeliness约束代码 (line 377-409):")
with open(os.path.join(BASE_DIR, 'src/solvers/question4/solve_problem4_loss.py'), 'r', encoding='utf-8') as f:
    lines_det = f.readlines()
for i in range(376, 410):
    if i < len(lines_det):
        print(f"  {i+1}: {lines_det[i]}", end='')