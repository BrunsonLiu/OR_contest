"""
深入对比两个模型的约束差异，找出gap的根本原因
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
all_wh_names = cdc_names + rdc_names
customer_cities = df_customer['Name'].tolist()
skus = ['im', 'dm']
sku_cdc = {'im': port_cdc, 'dm': inland_cdc}
cdc_sku = {port_cdc: 'im', inland_cdc: 'dm'}

cap = {}; proc_cost = {}; open_cost = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']
    proc_cost[row['Name']] = row['Processing_fee']
    open_cost[row['Name']] = row['Opening_fee']

# 确定性模型的单向矩阵
dist_oneway = {}
time_oneway = {}
for _, row in df_matrix.iterrows():
    dist_oneway[(row['From'], row['To'])] = row['Distance']
    time_oneway[(row['From'], row['To'])] = row['Duration']

# 鲁棒模型的对称矩阵
dist_sym = {}
dur_sym = {}
for _, row in df_matrix.iterrows():
    dist_sym[(row['From'], row['To'])] = row['Distance']
    dist_sym[(row['To'], row['From'])] = row['Distance']
    dur_sym[(row['From'], row['To'])] = row['Duration']
    dur_sym[(row['To'], row['From'])] = row['Duration']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

def calculate_loss_cost(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

# ============================================
# 核心发现1: df_matrix的方向性
# ============================================
print("=" * 70)
print("核心发现1: df_matrix.csv的条目方向性分析")
print("=" * 70)

# 检查From和To列的值类型
from_values = df_matrix['From'].unique()
to_values = df_matrix['To'].unique()

print(f"From列唯一值数: {len(from_values)}")
print(f"To列唯一值数: {len(to_values)}")

# 检查From和To的关系
from_wh_count = sum(1 for v in from_values if v in all_wh_names)
to_wh_count = sum(1 for v in to_values if v in all_wh_names)
from_cust_count = sum(1 for v in from_values if v in customer_cities)
to_cust_count = sum(1 for v in to_values if v in customer_cities)

print(f"From中仓库数: {from_wh_count}, To中仓库数: {to_wh_count}")
print(f"From中客户数: {from_cust_count}, To中客户数: {to_cust_count}")

# 关键问题: df_matrix是从仓库到客户的单向还是双向?
# 如果From是仓库，To是客户，那RDC->RDC的调拨距离在哪里?
rdc_to_rdc_in_from = 0
rdc_to_rdc_in_to = 0
cdc_to_rdc_in_from = 0
cdc_to_rdc_in_to = 0

for _, row in df_matrix.iterrows():
    f, t = row['From'], row['To']
    if f in rdc_names and t in rdc_names:
        rdc_to_rdc_in_from += 1
    if f in cdc_names and t in rdc_names:
        cdc_to_rdc_in_from += 1
    if f in rdc_names and t in cdc_names:
        cdc_to_rdc_in_to += 1

print(f"\nRDC->RDC条目(From是RDC): {rdc_to_rdc_in_from}")
print(f"CDC->RDC条目(From是CDC): {cdc_to_rdc_in_from}")
print(f"RDC->CDC条目(From是RDC, To是CDC): {cdc_to_rdc_in_to}")

# ============================================
# 核心发现2: 确定性模型中dist矩阵的构建方式
# ============================================
print("\n" + "=" * 70)
print("核心发现2: 确定性模型dist矩阵的条目分布")
print("=" * 70)

# 确定性模型只存储From->To
# 关键问题: u变量的目标系数用dist.get((wh, store), 0)
# 这意味着需要(wh, store)条目存在

missing_wh_to_cust = []
for wh in all_wh_names:
    for c in customer_cities:
        if (wh, c) not in dist_oneway:
            missing_wh_to_cust.append((wh, c))

print(f"缺失(wh, customer)距离条目: {len(missing_wh_to_cust)}")
if missing_wh_to_cust:
    print(f"示例: {missing_wh_to_cust[:5]}")

# ============================================
# 核心发现3: 对比两个模型实际使用的距离值
# ============================================
print("\n" + "=" * 70)
print("核心发现3: 两个模型对共同u变量的目标系数对比")
print("=" * 70)

# 构建两个模型实际使用的u变量集合
det_u_vars = set()
robust_u_vars = set()

for t in range(T):
    for c in customer_cities:
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            eligible = [sku_cdc[s]] + rdc_names
            for wh in eligible:
                det_u_vars.add((t, wh, c, s))
                dist_km = dist_sym.get((wh, c), 99999)
                if dist_km <= 5000:
                    robust_u_vars.add((t, wh, c, s))

common_vars = det_u_vars & robust_u_vars
only_det = det_u_vars - robust_u_vars
only_robust = robust_u_vars - det_u_vars

print(f"共同u变量: {len(common_vars)}")
print(f"仅确定性模型: {len(only_det)}")
print(f"仅鲁棒模型: {len(only_robust)}")

# 检查共同u变量的目标系数差异
obj_diff_count = 0
total_obj_diff = 0
max_diff = 0
max_diff_var = None

for (t, wh, c, s) in common_vars:
    qty = demand[t][(c, s)]

    # 确定性模型: 用单向矩阵
    d_det = dist_oneway.get((wh, c), 0)
    t_det = time_oneway.get((wh, c), 0)
    loss_det = calculate_loss_cost(t_det)
    obj_det = 1.45e-4 * d_det * qty + loss_det * qty + 2.0 * proc_cost.get(wh, 0) * qty

    # 鲁棒模型: 用对称矩阵
    d_rob = dist_sym.get((wh, c), 99999)
    t_rob = dur_sym.get((wh, c), 10000)
    loss_rob = calculate_loss_cost(t_rob)
    obj_rob = 1.45e-4 * d_rob * qty + loss_rob * qty + 2.0 * proc_cost.get(wh, 0) * qty

    diff = obj_det - obj_rob
    if abs(diff) > 0.001:
        obj_diff_count += 1
        total_obj_diff += diff
        if abs(diff) > max_diff:
            max_diff = abs(diff)
            max_diff_var = (t, wh, c, s)

print(f"\n目标系数不同的u变量: {obj_diff_count}")
print(f"目标系数差异总和: {total_obj_diff:.4f}")
if max_diff_var:
    t, wh, c, s = max_diff_var
    print(f"最大差异: {max_diff:.4f} at t={t}, {wh}->{c}({s})")

# ============================================
# 关键发现4: 检查df_matrix是否包含RDC->RDC条目
# ============================================
print("\n" + "=" * 70)
print("关键发现4: df_matrix中的RDC->RDC条目")
print("=" * 70)

rdc_rdc_entries = df_matrix[
    (df_matrix['From'].isin(rdc_names)) &
    (df_matrix['To'].isin(rdc_names))
]
print(f"RDC->RDC条目数: {len(rdc_rdc_entries)}")
if len(rdc_rdc_entries) > 0:
    print(rdc_rdc_entries.head(10))

# 检查: 鲁棒模型假设RDC之间不调拨，那确定性模型呢?
# 从solve_problem4_loss.py看，只定义了CDC->RDC的f变量
# 所以两个模型都没有RDC->RDC调拨

# ============================================
# 关键发现5: 时效约束的差异 (最可能的问题来源!)
# ============================================
print("\n" + "=" * 70)
print("关键发现5: 时效约束的差异分析")
print("=" * 70)

# 确定性模型: 对每个u变量
#   如果 travel_time <= 600: v >= u (即 u - v <= 0)
#   如果 travel_time > 600: v + u <= 1

# 鲁棒模型: 对每个(c,s)对
#   v <= sum(u for wh where travel_time <= 600)

# 这两个模型是不等价的!
# 确定性模型: v_u=1 当且仅当 travel_time<=600 且 u=1 时
# 鲁棒模型: v 可以被多个仓库共同满足

TIMELINESS_THRESHOLD = 600

# 统计每个(c,s)有多少个快速仓库
fast_wh_counts = {}
slow_only = []
for c in customer_cities:
    for s in skus:
        fast_whs = []
        for wh in [sku_cdc[s]] + rdc_names:
            t = dur_sym.get((wh, c), 10000)
            if t <= TIMELINESS_THRESHOLD:
                fast_whs.append(wh)
        fast_wh_counts[(c, s)] = len(fast_whs)
        if len(fast_whs) == 0:
            slow_only.append((c, s))

print(f"有快速仓库的(c,s)对: {len(fast_wh_counts) - len(slow_only)}")
print(f"只有慢速仓库的(c,s)对: {len(slow_only)}")
print(f"示例只有慢速的: {slow_only[:5]}")

# ============================================
# 关键发现6: w约束的差异
# ============================================
print("\n" + "=" * 70)
print("关键发现6: w约束差异 (智能系统折扣)")
print("=" * 70)

# 确定性模型: w约束包括CDC和RDC
# 鲁棒模型: w约束只包括RDC

# CDC z/w的影响
print("CDC智能系统影响:")
for cdc in cdc_names:
    proc = proc_cost.get(cdc, 0)
    discount = 0.8 * proc
    print(f"  {cdc}: proc_cost={proc}, w折扣={discount:.4f}/吨")

# 如果确定性模型中CDC z=1且w>0, 则可节省大量成本
# 而鲁棒模型完全没有这个选项

# ============================================
# 核心发现7: 重新分析约束数量差异
# ============================================
print("\n" + "=" * 70)
print("核心发现7: 重新分析约束数量差异")
print("=" * 70)

n_demand_per_t = len(demand[0])
n_u_det_per_t = 0
n_u_rob_per_t = 0
n_u_cdc_per_t = 0
n_u_rdc_per_t = 0

for (c, s) in demand[0]:
    eligible = [sku_cdc[s]] + rdc_names
    n_u_det_per_t += len(eligible)
    for wh in eligible:
        dist_km = dist_sym.get((wh, c), 99999)
        if dist_km <= 5000:
            n_u_rob_per_t += 1
        if wh in cdc_names:
            n_u_cdc_per_t += 1
        else:
            n_u_rdc_per_t += 1

print(f"每周期需求对数: {n_demand_per_t}")
print(f"每周期u变量(确定性): {n_u_det_per_t}")
print(f"每周期u变量(鲁棒,含dist过滤): {n_u_rob_per_t}")
print(f"  其中CDC的u变量: {n_u_cdc_per_t}")
print(f"  其中RDC的u变量: {n_u_rdc_per_t}")

# service_open约束差异
print(f"\nservice_open约束:")
print(f"  确定性模型: {T * n_u_det_per_t} (每个u变量一个)")
print(f"  鲁棒模型: {T * n_u_rdc_per_t} (只有RDC的u变量)")
print(f"  差异: {T * (n_u_det_per_t - n_u_rdc_per_t)}")

# 关键问题: 鲁棒模型对CDC的u变量没有service_open约束!
# 这意味着CDC可以"服务"任何门店，即使CDC的开设状态...

# 等等，CDC是"必开"的(y=1)，所以u≤y对CDC总是满足的
# 但这仍然改变了约束的数量和结构

# ============================================
# 最终发现: 目标函数中z变量成本的差异
# ============================================
print("\n" + "=" * 70)
print("最终发现: z变量(智能系统采购)差异")
print("=" * 70)

# 确定性模型: z变量对所有仓库(CDC+RDC), obj=1.5
# 鲁棒模型: z变量只对RDC, obj=1.5

# CDC z变量的影响
# 确定性模型可能购买CDC的智能系统，获得处理费折扣
# 鲁棒模型完全没有这个选项

# 检查CDC proc_cost
print("CDC处理费:")
for cdc in cdc_names:
    print(f"  {cdc}: proc_cost={proc_cost.get(cdc, 0)}")

# CDC proc_cost约为0.0065-0.0075, 相比RDC(0.00635-0.0075)差异很小
# 所以CDC z/w的影响应该很小

# ============================================
# 重新审视: 到底是什么导致gap?
# ============================================
print("\n" + "=" * 70)
print("重新审视: 可能的gap来源")
print("=" * 70)

print("""
根据之前的诊断:
- 确定性模型LP lower bound: 232,543
- 鲁棒模型MIP solution: 225,122

如果鲁棒模型是确定性模型的松弛版本，那应该:
1. 鲁棒模型MIP >= 确定性模型LP (对于同一问题)
2. 但我们看到相反: 225,122 < 232,543

这说明鲁棒模型求解的是**不同的(更弱的)问题**!

可能的原因:
1. 鲁棒模型有错误的约束 (太松)
2. 鲁棒模型有错误的目标系数 (成本太低)
3. 鲁棒模型有缺失的约束
""")

# ============================================
# 检查: 读取鲁棒模型的原始结果文件
# ============================================
print("\n" + "=" * 70)
print("检查: 鲁棒模型原始结果分析")
print("=" * 70)

import json
robust_result_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust', 'robust_results.json')
if os.path.exists(robust_result_file):
    with open(robust_result_file, 'r') as f:
        robust_results = json.load(f)

    # 找到Γ=0%的结果
    for r in robust_results:
        if abs(r['gamma'] - 0.0) < 0.001:
            print(f"Γ=0% 结果:")
            print(f"  总成本: {r['total_cost']:.2f}")
            print(f"  开设仓库数: {r.get('opened_wh_count', 'N/A')}")
            print(f"  智能系统数: {r.get('smart_count', 'N/A')}")
            if 'cost_breakdown' in r:
                print(f"  成本分解:")
                for k, v in r['cost_breakdown'].items():
                    print(f"    {k}: {v:.2f}")
            break
else:
    print(f"文件不存在: {robust_result_file}")

# ============================================
# 检查: 读取确定性模型的原始结果文件
# ============================================
print("\n" + "=" * 70)
print("检查: 确定性模型原始结果分析")
print("=" * 70)

det_result_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result', '仓网业务表现文件_汇总.csv')
if os.path.exists(det_result_file):
    df_det = pd.read_csv(det_result_file)
    print(f"列名: {df_det.columns.tolist()}")
    print(f"形状: {df_det.shape}")
    if 'Total_Cost' in df_det.columns:
        total_cost_det = df_det['Total_Cost'].sum()
        print(f"确定性模型总成本: {total_cost_det:.2f}")
    elif '总成本' in df_det.columns:
        total_cost_det = df_det['总成本'].sum()
        print(f"确定性模型总成本: {total_cost_det:.2f}")
    print(df_det.head())
else:
    print(f"文件不存在: {det_result_file}")
