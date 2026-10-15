"""
关键诊断: 检查容量约束的差异
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
df_proc = pd.read_csv(os.path.join(INPUT_DIR, 'df_proc.csv'))
df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))

cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

cap = {}
proc_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

# ============================================
# 关键发现: 容量分析
# ============================================
print("=" * 70)
print("容量分析: CDC容量 vs 需求")
print("=" * 70)

# 计算每周期每个SKU的总需求
cdc_sku = {'gang-kou-CDC': 'im', 'nei-lu-CDC': 'dm'}

for t in range(T):
    print(f"\n周期 {t}:")
    total_demand_t = 0
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        cap_cdc = cap.get(cdc, 0)
        demand_cdc = sum(demand[t][(c, s)] for c in df_customer['Name'].tolist() if (c, s) in demand[t])
        print(f"  {cdc}({s}): 容量={cap_cdc:.0f}, 需求={demand_cdc:.2f}, 剩余容量={cap_cdc-demand_cdc:.2f}")
        total_demand_t += demand_cdc

# 计算7天总需求和容量
total_7d = sum(sum(demand[t].values()) for t in range(T))
cdc_total_cap_7d = sum(cap.get(cdc, 0) for cdc in cdc_names) * T
rdc_total_cap = sum(cap.get(rdc, 0) for rdc in rdc_names)

print(f"\n7天总需求: {total_7d:.2f} 吨")
print(f"CDC 7天总容量: {cdc_total_cap_7d:.0f} 吨")
print(f"RDC每天总容量: {rdc_total_cap:.0f} 吨")
print(f"RDC 7天总容量: {rdc_total_cap * T:.0f} 吨")

# ============================================
# 关键问题: 鲁棒模型的CDC容量约束是否正确?
# ============================================
print("\n" + "=" * 70)
print("关键问题: CDC容量约束分析")
print("=" * 70)

print("""
从solve_problem4_robust.py的CDC容量约束(line 574-599):
- 约束形式: Σ u·qty + Σ f ≤ cap_cdc
- 其中 u 是 CDC 直接服务门店的量
- f 是 CDC 调拨到 RDC 的量

问题: CDC容量约束是否同时限制了直接服务和调拨?

如果是，那么:
- CDC直接服务门店的量 + CDC调拨量 ≤ CDC容量

如果是确定性模型，还会有额外的约束...
""")

# ============================================
# 检查确定性模型的CDC容量约束
# ============================================
print("\n" + "=" * 70)
print("确定性模型的CDC容量约束")
print("=" * 70)

print("""
从solve_problem4_loss.py的CDC容量约束(line 350-375):

约束形式: -cap[cdc] * y_cdc + Σ u·qty + Σ f ≤ 0

其中:
- y_cdc 是 CDC 的开设变量
- 对于 CDC, y_cdc = 1 (因为 lb = ub = 1)

所以约束等价于: Σ u·qty + Σ f ≤ cap[cdc]

这部分与鲁棒模型相同!
""")

# ============================================
# 真正的问题: 鲁棒模型的open_new约束
# ============================================
print("\n" + "=" * 70)
print("真正的问题: open_new约束的差异")
print("=" * 70)

print("""
从诊断v7的输出:
- 确定性模型 open_new约束: 360个
- 鲁棒模型 open_new约束: 126个

open_new约束控制仓库开设逻辑:
- 确定性模型使用3条约束:
  open_new ≤ y (line 281-283)
  open_new ≤ 1 - y_prev (line 284-286)
  open_new ≥ y - y_prev (line 287-289)

- 鲁棒模型使用2条约束 (line 157-162):
  open_new_0 = y_0
  open_new_t = y_t - y_{t-1}

这些约束形式不同!

确定性模型用3条约束来正确建模 open_new = y AND NOT y_prev
鲁棒模型用2条约束: open_new = y - y_{t-1}

但数学上是等价的!
""")

# ============================================
# 真正的问题: CDC的服务-开设约束
# ============================================
print("\n" + "=" * 70)
print("真正的问题: CDC的u变量是否有service_open约束?")
print("=" * 70)

print("""
鲁棒模型的service_open约束(line 459-469):
- 只对 RDC 的 u 变量添加 u ≤ y 约束
- 对 CDC 的 u 变量没有添加!

确定性模型的service_open约束(line 317-326):
- 对所有仓库(CDC+RDC)的 u 变量添加 u ≤ y 约束

这意味着:
- 在鲁棒模型中，CDC可以"服务"任何门店，即使CDC的开设状态没有正确设置
- 但 CDC 是必开的(y=1)，所以 u ≤ y 总是满足的

这不是问题!
""")

# ============================================
# 核心问题: 时效约束的差异
# ============================================
print("\n" + "=" * 70)
print("核心问题: 时效约束的差异")
print("=" * 70)

print("""
确定性模型时效约束(line 377-409):
1. 对每个(wh, store, sku)添加:
   - 如果 travel_time ≤ 600: u ≤ v (即 v ≥ u)
   - 如果 travel_time > 600: u + v ≤ 1 (即 v = 0)

2. 整体时效满足率约束:
   Σ v * qty ≥ 0.95 * Σ demand

鲁棒模型时效约束(line 601-638):
1. v约束: v ≤ Σ u (for fast_wh)
2. 整体时效满足率约束:
   Σ v * qty ≥ 0.95 * worst_total_demand

问题: worst_total_demand 与 Σ demand 是否相同?
""")

# 计算worst_total_demand vs nominal_demand
print("\nworst_total_demand vs nominal_demand (Γ=0%):")

df_past = pd.read_csv(os.path.join(INPUT_DIR, 'df_past_order.csv'))
city_sku_resid_std = {}
for _, row in df_past.iterrows():
    city, sku = row['Name'], row['SKU']
    vals = row[[c for c in df_past.columns if c not in ['Name', 'SKU']]].values.astype(float)
    std_resid = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
    city_sku_resid_std[(city, sku)] = max(std_resid, 0.01)

def compute_worst_case_total_demand(t, gamma_fraction):
    keys = list(demand[t].keys())
    nominal_sum = sum(demand[t][k] for k in keys)
    deltas = [city_sku_resid_std.get(k, 0.1) * 2.0 for k in keys]
    deltas.sort(reverse=True)
    n_total = len(deltas)
    gamma_int = min(int(gamma_fraction * n_total), n_total)
    gamma_frac = (gamma_fraction * n_total) - gamma_int
    robust_extra = sum(deltas[:gamma_int])
    if gamma_int < n_total and gamma_frac > 0:
        robust_extra += gamma_frac * deltas[gamma_int]
    return nominal_sum + robust_extra

for t in range(T):
    nominal = sum(demand[t].values())
    worst_0 = compute_worst_case_total_demand(t, 0.0)
    worst_5 = compute_worst_case_total_demand(t, 0.05)
    print(f"  t={t}: nominal={nominal:.2f}, worst(Γ=0)={worst_0:.2f}, worst(Γ=5%)={worst_5:.2f}")

# ============================================
# 最终结论
# ============================================
print("\n" + "=" * 70)
print("最终结论")
print("=" * 70)

print("""
当Γ=0%时:
1. worst_total_demand = nominal_demand (相同)
2. p和q变量不参与约束 (因为gamma_used = 0)
3. open_new约束形式不同但数学等价
4. service_open约束对CDC没有区别 (因为CDC必开)
5. 时效约束RHS相同

那为什么两个模型给出不同的结果?

可能的原因:
1. 求解器找到了不同的局部最优解
2. 某个模型有bug导致找到不可行但被接受的解
3. MIP gap容差导致次优解被接受

建议:
1. 将两个模型的MIP gap容差都设为0
2. 增加求解时间限制
3. 比较两个模型的LP relaxation bound
4. 检查求解器日志中的节点数和分支数
""")
