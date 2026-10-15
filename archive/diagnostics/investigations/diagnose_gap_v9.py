"""
深入分析: 检查两个模型CDC容量约束的差异
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
customer_cities = df_customer['Name'].tolist()
skus = ['im', 'dm']
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

cap = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

# ============================================
# CDC容量约束分析
# ============================================
print("=" * 70)
print("CDC容量约束分析")
print("=" * 70)

# 确定性模型的CDC容量约束 (来自solve_problem4_loss.py line 350-375):
# indices = [var_y] + 门店配送量 + CDC调拨量
# sense = 'L', rhs = 0
# 即: -cap[y] + Σ门店u·qty + Σ调拨f ≤ 0

# 鲁棒模型的CDC容量约束 (来自solve_problem4_robust.py line 574-599):
# indices_cdc = 门店配送量 + 调拨量
# sense = 'L', rhs = cap_cdc

# 关键差异: 确定性模型有 y_t^cdc 变量, 但 CDC 是必开的(lb=1)
# 让我检查: 确定性模型是否真的限制了 CDC 容量

print("\nCDC容量:")
for cdc in cdc_names:
    print(f"  {cdc}: {cap.get(cdc, 0)} 吨")

print("\n每周期各CDC的名义需求量:")
for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        total_demand = sum(demand[t][(c, s)] for c in customer_cities if (c, s) in demand[t])
        print(f"  t={t}, {cdc}({s}): {total_demand:.2f} 吨")

print("\n各CDC的总容量 vs 名义需求:")
for cdc in cdc_names:
    s = cdc_sku[cdc]
    cap_cdc = cap.get(cdc, 0)
    total_demand_per_t = sum(demand[t][(c, s)] for t in range(T) for c in customer_cities if (c, s) in demand[t])
    avg_demand_per_t = total_demand_per_t / T
    print(f"  {cdc}: 容量={cap_cdc:.0f}, 平均每周期需求={avg_demand_per_t:.2f}, "
          f"容量/需求比={cap_cdc/avg_demand_per_t:.2f}")

# ============================================
# 关键问题: 鲁棒模型是否正确处理CDC直接服务?
# ============================================
print("\n" + "=" * 70)
print("关键问题: 鲁棒模型中CDC的u变量约束分析")
print("=" * 70)

# 在鲁棒模型中，CDC的u变量应该受到容量约束限制
# 但CDC容量约束是: Σu·qty + Σf ≤ cap
# 这意味着: 如果CDC直接服务大量门店，可能无法同时满足调拨需求

# 让我检查: CDC容量是否足够同时服务门店+调拨RDC?
print("\n检查CDC容量是否足够:")
for t in range(0, 1):  # 只看第一个周期
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        cap_cdc = cap.get(cdc, 0)

        # 计算如果所有门店都由CDC服务，需要多少容量
        direct_service_demand = sum(demand[t][(c, s)] for c in customer_cities if (c, s) in demand[t])

        # 计算RDC的调拨需求
        rdc_transfer_demand = len(rdc_names) * demand[t].get((customer_cities[0], s), 0) * len(customer_cities) / 10  # 粗略估计

        print(f"\n  {cdc} (周期{t}):")
        print(f"    容量: {cap_cdc:.0f}")
        print(f"    直接服务门店需求: {direct_service_demand:.2f}")
        print(f"    如果完全直接服务，需求/容量比: {direct_service_demand/cap_cdc:.2%}")

# ============================================
# 关键发现: 鲁棒模型缺少CDC的z/w约束!
# ============================================
print("\n" + "=" * 70)
print("关键发现: z/w约束差异")
print("=" * 70)

# 确定性模型有CDC的z/w变量:
# - z_cdc: 智能系统采购, obj=1.5
# - w_cdc: 处理量折扣, obj=-0.8*proc_cost

# 鲁棒模型没有CDC的z/w变量!

# 让我计算CDC z/w的潜在影响
print("\nCDC智能系统影响分析:")
for cdc in cdc_names:
    proc = df_proc[df_proc['Name'] == cdc]['Processing_fee'].values[0]
    cap_cdc = cap.get(cdc, 0)
    s = cdc_sku[cdc]

    # 如果购买CDC智能系统, 7天总处理量对应的折扣
    total_demand_7d = sum(demand[t][(c, s)] for t in range(T) for c in customer_cities if (c, s) in demand[t])

    # 智能系统成本
    smart_cost = 1.5  # 万元
    # 智能系统折扣
    discount_per_ton = 0.8 * proc
    total_discount = discount_per_ton * total_demand_7d
    net_saving = total_discount - smart_cost

    print(f"\n  {cdc}:")
    print(f"    proc_cost: {proc}")
    print(f"    7天总处理量: {total_demand_7d:.2f} 吨")
    print(f"    智能系统成本: {smart_cost:.2f} 万元")
    print(f"    处理费折扣: {discount_per_ton:.4f} 万元/吨")
    print(f"    总折扣价值: {total_discount:.2f} 万元")
    print(f"    净节省: {net_saving:.2f} 万元")

# ============================================
# 核心问题: 鲁棒模型在Γ=0%时的目标函数是否正确?
# ============================================
print("\n" + "=" * 70)
print("核心问题: 鲁棒模型目标函数分析")
print("=" * 70)

# 在solve_problem4_robust.py中:
# 1. 基础目标函数设置 (lines 696-740)
# 2. 鲁棒目标函数项 (lines 742-766) - Γ>0时才添加
# 3. 鲁棒目标约束 (lines 768-804) - Γ>0时才添加

# 当Γ=0%时:
# - 基础目标函数应该正确
# - 没有额外的鲁棒目标项
# - 没有额外的鲁棒目标约束

# 但让我检查基础目标函数的设置
# 根据代码 (lines 700-715), 对每个u变量设置:
# obj = 1.45e-4 * dist * qty + loss_cost * qty + 2.0 * proc_cost * qty

# 这与确定性模型的目标系数一致

# 但是! 关键问题: w变量的目标系数
# 确定性模型 (line 229): obj = -0.8 * proc_cost.get(wh, 0.0)
# 鲁棒模型 (line 735): obj_contributions[w_var] -= 0.8 * proc_cost.get(wh, 0.0)

# 两者都只对RDC的w变量设置折扣!
# CDC的w变量在两个模型中都... 等等

# 让我重新检查鲁棒模型
# 鲁棒模型只有RDC的w变量 (line 363-366), 没有CDC的w变量!
# 确定性模型有所有仓库的w变量 (line 223-232)

# 所以当确定性模型购买CDC智能系统时，可以获得CDC处理费折扣
# 但鲁棒模型完全没有这个选项!

print("""
总结: CDC z/w变量差异

确定性模型:
  - 有所有仓库(CDC+RDC)的z变量
  - 有所有仓库(CDC+RDC)的w变量
  - z约束: z ≤ sum(y_t) (line 291-299)
  - w约束1: w ≤ 总出库量 (line 418-436)
  - w约束2: w ≤ z * cap (line 437-441)

鲁棒模型:
  - 只有RDC的z变量 (line 323-325)
  - 只有RDC的w变量 (line 363-366)
  - z约束: z ≤ sum(y_t) (line 640-649)
  - w约束: w ≤ 总出库量, w ≤ z*cap (line 652-674)

影响:
  确定性模型可以选择购买CDC智能系统，获得处理费折扣
  鲁棒模型完全没有这个选项

但由于CDC proc_cost较小 (0.0065-0.0075)，这个影响可能不大
""")

# ============================================
# 真正的问题: 检查鲁棒模型的CDC容量约束是否使用worst-case demand
# ============================================
print("\n" + "=" * 70)
print("真正的问题: CDC容量约束的RHS")
print("=" * 70)

def compute_worst_case_total_demand(t, gamma_fraction, sku_filter=None):
    """从鲁棒模型复制的函数"""
    forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
    keys = [(row['Customer'], row['SKU']) for _, row in df_forecast.iterrows()
            if (row['Customer'], row['SKU']) in demand[t]]
    if sku_filter:
        keys = [k for k in keys if k[1] == sku_filter]

    nominal_sum = sum(demand[t][k] for k in keys)

    # 残差标准差
    import numpy as np
    df_past = pd.read_csv(os.path.join(INPUT_DIR, 'df_past_order.csv'))
    city_sku_resid_std = {}
    for _, row in df_past.iterrows():
        city, sku = row['Name'], row['SKU']
        vals = row[[c for c in df_past.columns if c not in ['Name', 'SKU']]].values.astype(float)
        std_resid = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
        city_sku_resid_std[(city, sku)] = max(std_resid, 0.01)

    deltas = [city_sku_resid_std.get(k, 0.1) * 2.0 for k in keys]
    deltas.sort(reverse=True)

    n_total = len(deltas)
    gamma_int = min(int(gamma_fraction * n_total), n_total)
    gamma_frac = (gamma_fraction * n_total) - gamma_int

    robust_extra = sum(deltas[:gamma_int])
    if gamma_int < n_total and gamma_frac > 0:
        robust_extra += gamma_frac * deltas[gamma_int]

    return nominal_sum + robust_extra

print("\nCDC容量约束RHS计算:")
for t in range(T):
    for cdc in cdc_names:
        s = cdc_sku[cdc]
        cap_cdc = cap.get(cdc, 0)

        nominal = sum(demand[t][(c, s)] for c in customer_cities if (c, s) in demand[t])
        worst_0 = compute_worst_case_total_demand(t, 0.0, s)
        worst_005 = compute_worst_case_total_demand(t, 0.05, s)

        print(f"\n  t={t}, {cdc}({s}):")
        print(f"    容量: {cap_cdc:.0f}")
        print(f"    名义需求: {nominal:.2f}")
        print(f"    Γ=0% worst-case: {worst_0:.2f}")
        print(f"    Γ=5% worst-case: {worst_005:.2f}")

# ============================================
# 最终诊断: 运行一个小规模的LP来验证
# ============================================
print("\n" + "=" * 70)
print("最终诊断: 构建并求解简化的LP模型")
print("=" * 70)

import cplex

# 简化模型: 只考虑一个周期，固定开设状态，检查最优解
problem = cplex.Cplex()
problem.objective.set_sense(problem.objective.sense.minimize)

# 变量
var_idx = {}
var_count = 0

# y变量 (固定开设所有RDC)
for rdc in rdc_names:
    name = f'y_{rdc}'
    problem.variables.add(obj=[0.0], lb=[1.0], ub=[1.0],
                         types=[problem.variables.type.binary], names=[name])
    var_idx[name] = var_count
    var_count += 1

# u变量
for c in customer_cities:
    for s in skus:
        if (c, s) not in demand[0]:
            continue
        qty = demand[0][(c, s)]
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            name = f'u_{wh}_{c}_{s}'
            dist_val = 999  # 简化
            proc = df_proc[df_proc['Name'] == wh]['Processing_fee'].values[0]
            obj = 1.45e-4 * dist_val * qty + 2.0 * proc * qty  # 简化目标
            problem.variables.add(obj=[obj], lb=[0.0], ub=[1.0],
                                 types=[problem.variables.type.binary], names=[name])
            var_idx[name] = var_count
            var_count += 1

print(f"变量数: {var_count}")

# 单源约束
lin_exprs = []
senses = []
rhs = []

for c in customer_cities:
    for s in skus:
        if (c, s) not in demand[0]:
            continue
        indices = []
        coeffs = []
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            name = f'u_{wh}_{c}_{s}'
            if name in var_idx:
                indices.append(var_idx[name])
                coeffs.append(1.0)
        if indices:
            lin_exprs.append(cplex.SparsePair(ind=indices, val=coeffs))
            senses.append('E')
            rhs.append(1.0)

problem.linear_constraints.add(lin_expr=lin_exprs, senses=senses, rhs=rhs)

# 求解
problem.set_problem_name("simplified_test")
problem.parameters.timelimit.set(30)

try:
    problem.solve()
    status = problem.solution.get_status()
    obj = problem.solution.get_objective_value()
    print(f"简化模型求解状态: {status}")
    print(f"简化模型目标值: {obj:.2f}")
except Exception as e:
    print(f"求解失败: {e}")

print("\n结论: 需要完整重建两个模型进行对比")
