"""
精确对比: 两个模型的CDC容量约束
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
# 关键发现: 两个模型CDC容量约束的差异
# ============================================
print("=" * 70)
print("关键发现: CDC容量约束的精确对比")
print("=" * 70)

print("""
确定性模型 (solve_problem4_loss.py line 350-375):
  约束形式: -cap[y] + Σ(u·qty) + Σ(f) ≤ 0
  其中:
    - y 是 CDC 的开设变量
    - Σ(u·qty) 是直接服务门店的量
    - Σ(f) 是向 RDC 的调拨量

鲁棒模型 (solve_problem4_robust.py line 574-599):
  约束形式: Σ(u·qty) + Σ(f) ≤ cap
  其中:
    - 只有直接的 u 和 f 变量
    - 没有乘以 y (因为 CDC 必开，y=1)

问题: CDC 是否必开?
""")

# 检查CDC开设状态
print("\n检查CDC开设状态:")
for cdc in cdc_names:
    cdc_type = df_wh[df_wh['Name'] == cdc]['Type'].values[0]
    print(f"  {cdc}: Type={cdc_type}")

# 关键: 在确定性模型中，CDC的y变量lb=1, ub=1
# 所以约束中的 -cap[y] 实际上是 -cap*1 = -cap
# 这与鲁棒模型中的 RHS=cap 是等价的

print("""
结论: CDC容量约束在两个模型中是等价的 (当Γ=0%时)

那问题出在哪里?
""")

# ============================================
# 关键差异: f变量的约束
# ============================================
print("=" * 70)
print("关键差异: f变量的约束")
print("=" * 70)

# 检查: f变量是否受到容量约束的限制?
print("""
确定性模型:
  - CDC容量约束包含 Σf
  - f ≤ cap - Σu (隐式通过容量约束)
  - 没有显式的 f ≤ ... 约束

鲁棒模型:
  - CDC容量约束包含 Σf
  - f ≤ cap - Σu (隐式通过容量约束)
  - 没有显式的 f ≤ ... 约束

这部分是相同的
""")

# ============================================
# 真正的问题: 让我检查鲁棒模型的结果文件
# ============================================
print("=" * 70)
print("分析鲁棒模型的结果文件")
print("=" * 70)

import json

robust_result_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust', 'robust_results.json')
if os.path.exists(robust_result_file):
    with open(robust_result_file, 'r') as f:
        robust_results = json.load(f)

    for r in robust_results:
        if abs(r['gamma'] - 0.0) < 0.001:
            print(f"Γ=0% 结果:")
            print(f"  总成本: {r['total_cost']:.2f}")
            print(f"  开设仓库数: {r.get('opened_wh_count', 'N/A')}")
            if 'opened_wh_names' in r:
                print(f"  开设仓库: {r['opened_wh_names']}")
            if 'smart_wh_names' in r:
                print(f"  智能系统: {r['smart_wh_names']}")
            if 'cost_breakdown' in r:
                print(f"  成本分解:")
                for k, v in r['cost_breakdown'].items():
                    print(f"    {k}: {v:.2f}")
            break

# ============================================
# 真正的问题: 让我检查鲁棒模型的约束实现
# ============================================
print("\n" + "=" * 70)
print("深入检查: 鲁棒模型CDC容量约束的实现")
print("=" * 70)

# 从solve_problem4_robust.py读取CDC容量约束代码
with open(os.path.join(BASE_DIR, 'src/solvers/question4/solve_problem4_robust.py'), 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到CDC容量约束部分
print("\n鲁棒模型CDC容量约束代码 (line 574-599):")
for i in range(573, min(600, len(lines))):
    print(f"  {i+1}: {lines[i]}", end='')

# 检查: 这个约束是否正确?
# 它应该包含:
# 1. Σ u_t_cdc_c_s * qty  (CDC直接服务门店)
# 2. Σ f_t_cdc_rdc_s      (CDC调拨到RDC)

# 让我检查代码中是否包含了这两项
print("\n" + "=" * 70)
print("检查鲁棒模型中f变量的定义")
print("=" * 70)

print("\n鲁棒模型f变量定义代码 (line 342-351):")
for i in range(341, min(352, len(lines))):
    print(f"  {i+1}: {lines[i]}", end='')

# 关键问题: f变量是按照 (t, cdc, rdc, s) 创建的
# 目标系数是通过 set_linear 设置的

# 让我检查鲁棒模型中f变量的目标系数是否正确
print("\n" + "=" * 70)
print("检查f变量目标系数的设置")
print("=" * 70)

print("\n鲁棒模型f变量目标系数设置 (line 717-729):")
for i in range(716, min(730, len(lines))):
    print(f"  {i+1}: {lines[i]}", end='')

# 关键发现: f变量的目标系数只包括CDC的proc_cost
# 但确定性模型中f变量的目标系数也只包括CDC的proc_cost
# 所以这部分应该是相同的

# ============================================
# 最终诊断: 重新计算目标函数中的成本
# ============================================
print("\n" + "=" * 70)
print("最终诊断: 重新计算两个模型的目标函数")
print("=" * 70)

# 读取距离矩阵
dist_sym = {}
dur_sym = {}
for _, row in df_matrix.iterrows():
    dist_sym[(row['From'], row['To'])] = row['Distance']
    dist_sym[(row['To'], row['From'])] = row['Distance']
    dur_sym[(row['From'], row['To'])] = row['Duration']
    dur_sym[(row['To'], row['From'])] = row['Duration']

proc_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

def calculate_loss_cost(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000.0

# 计算7天总需求
total_demand = 0
for t in range(T):
    for (c, s), qty in demand[t].items():
        total_demand += qty

print(f"7天总需求量: {total_demand:.2f} 吨")

# 计算各成本项的理论最小值 (假设完美分配)
print("\n理论成本估计:")

# 1. 运输成本 (warehouse-to-customer)
# 假设平均距离1000km, 单价1.45e-4
est_trans_cost = 1.45e-4 * 1000 * total_demand
print(f"  运输成本(假设avg_dist=1000km): {est_trans_cost:.2f} 万元")

# 2. 处理成本
est_proc_cost = 2.0 * np.mean(list(proc_cost.values())) * total_demand
print(f"  处理成本(假设avg_proc_cost=0.007): {est_proc_cost:.2f} 万元")

# 3. 损耗成本 (假设50%门店超过500分钟，平均超时100分钟)
est_loss = 0.2 * 100**2 / 10000 * total_demand * 0.5
print(f"  损耗成本(粗略估计): {est_loss:.2f} 万元")

# 4. 开仓成本 (16个RDC)
est_open_cost = 16 * 25  # 假设平均开仓成本25万
print(f"  开仓成本(16个RDC): {est_open_cost:.2f} 万元")

# 5. 智能系统成本
est_smart_cost = 16 * 1.5  # 假设16个RDC都买智能系统
print(f"  智能系统成本: {est_smart_cost:.2f} 万元")

total_est = est_trans_cost + est_proc_cost + est_loss + est_open_cost + est_smart_cost
print(f"\n理论总成本: {total_est:.2f} 万元")
print(f"确定性模型成本: 233,949 万元")
print(f"鲁棒模型成本: 225,122 万元")

# ============================================
# 结论: 问题可能出在鲁棒模型的某个约束上
# ============================================
print("\n" + "=" * 70)
print("结论: 需要验证鲁棒模型Γ=0%时的解是否满足确定性模型的约束")
print("=" * 70)

# 读取鲁棒模型的解
if os.path.exists(robust_result_file):
    with open(robust_result_file, 'r') as f:
        robust_results = json.load(f)

    for r in robust_results:
        if abs(r['gamma'] - 0.0) < 0.001:
            if 'solution' in r:
                print("\n鲁棒模型解中的开设仓库:")
                for wh, val in r['solution'].items():
                    if wh.startswith('y_') and val > 0.5:
                        print(f"  {wh}: {val}")

            # 检查是否有CDC开设信息
            if 'cdc_direct_service' in str(r):
                print(f"\nCDC直接服务信息: {r.get('cdc_direct_service', 'N/A')}")
            break

print("""
下一步: 需要将鲁棒模型Γ=0%的解代入确定性模型约束中
检查是否有约束被违反

可能的问题:
1. 鲁棒模型可能违反了确定性模型的某个约束
2. 约束差异导致不同的最优解
3. 目标函数系数设置错误
""")
