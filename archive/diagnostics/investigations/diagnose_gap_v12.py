"""
关键诊断: 检查时效满足率约束的差异
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

# 读取距离和时间
dist = {}
time_matrix = {}
for _, row in df_matrix.iterrows():
    dist[(row['From'], row['To'])] = row['Distance']
    time_matrix[(row['From'], row['To'])] = row['Duration']

TIMELINESS_THRESHOLD = 600

# ============================================
# 关键发现: 检查每个仓库到每个客户的时效情况
# ============================================
print("=" * 70)
print("关键发现: 各仓库到各客户的时效情况")
print("=" * 70)

# 检查每个客户有多少个仓库可以在600分钟内到达
fast_wh_counts = {}
slow_wh_counts = {}
for c in customer_cities:
    fast_whs = []
    slow_whs = []
    for wh in cdc_names + rdc_names:
        t = time_matrix.get((wh, c), 10000)
        if t <= TIMELINESS_THRESHOLD:
            fast_whs.append((wh, t))
        else:
            slow_whs.append((wh, t))
    fast_wh_counts[c] = len(fast_whs)
    slow_wh_counts[c] = len(slow_whs)

# 统计
only_slow = [c for c in customer_cities if fast_wh_counts[c] == 0]
print(f"\n没有快速仓库可达的客户数: {len(only_slow)}")
if only_slow:
    print(f"  示例: {only_slow[:5]}")

has_fast = [c for c in customer_cities if fast_wh_counts[c] > 0]
print(f"有快速仓库可达的客户数: {len(has_fast)}")

# 快速仓库数量分布
from collections import Counter
dist_count = Counter(fast_wh_counts.values())
print(f"\n快速仓库数量分布:")
for k, v in sorted(dist_count.items()):
    print(f"  {k}个快速仓库: {v}个客户")

# ============================================
# 关键问题: 检查时效约束的RHS
# ============================================
print("\n" + "=" * 70)
print("关键问题: 时效约束的RHS计算")
print("=" * 70)

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]
T = len(forecast_dates)
demand = {t: {} for t in range(T)}
for _, row in df_forecast.iterrows():
    city = row['Customer']
    sku = row['SKU']
    for t_idx, date_col in enumerate(forecast_dates):
        demand[t_idx][(city, sku)] = float(row[date_col])

# 计算每个周期需要满足的时效需求量
TIMELINESS_RATIO = 0.95

print(f"\n每周期时效约束RHS (95% of total demand):")
for t in range(T):
    total_demand_t = sum(demand[t].values())
    required = TIMELINESS_RATIO * total_demand_t
    print(f"  t={t}: 总需求={total_demand_t:.2f}, 需要满足={required:.2f}")

# ============================================
# 关键发现: 检查鲁棒模型是否强制了时效满足率
# ============================================
print("\n" + "=" * 70)
print("关键发现: 检查鲁棒模型的时效约束")
print("=" * 70)

# 从solve_problem4_robust.py看:
# Line 624-638: 时效overall约束
# Line 626-627: required_tonnage = TIMELINESS_RATIO * worst_total
# 其中worst_total = compute_worst_case_total_demand(t, gamma_fraction)

# 当Γ=0%时，worst_total = nominal_total
# 所以时效约束RHS = 0.95 * nominal_total

# 但是! 这个约束是 Σ v * qty >= required
# v是二进制变量，表示是否满足时效

# 问题: 约束是否足够严格?
# 如果有足够的快速仓库可达，那么v=1
# 但如果没有快速仓库可达，那么v只能=0

# 让我检查是否有足够的快速仓库来满足95%需求
print("\n检查: 是否有足够的快速仓库容量来满足95%时效要求")

# 获取每个仓库的容量
cap = {}
for _, row in df_proc.iterrows():
    cap[row['Name']] = row['Capacity']

# 计算16个RDC的总容量
rdc_cap_sum = sum(cap.get(rdc, 0) for rdc in rdc_names)
print(f"\n16个RDC总容量: {rdc_cap_sum:.0f} 吨")

# 计算7天总需求
total_7d = sum(sum(demand[t].values()) for t in range(T))
print(f"7天总需求: {total_7d:.2f} 吨")

# 计算每天平均需求
avg_daily = total_7d / T
print(f"每天平均需求: {avg_daily:.2f} 吨")

# 检查容量是否足够
print(f"\n容量/平均日需求比: {rdc_cap_sum/avg_daily:.2f}")
print(f"7天容量: {rdc_cap_sum * T:.0f} 吨")
print(f"7天需求: {total_7d:.0f} 吨")

# ============================================
# 真正的问题: 检查两个模型的loss_cost计算差异
# ============================================
print("\n" + "=" * 70)
print("真正的问题: loss_cost计算公式对比")
print("=" * 70)

def calculate_loss_cost_det(minutes):
    """确定性模型使用这个"""
    if minutes <= 500:
        return 0.0
    else:
        loss_yuan = 0.2 * (minutes - 500) ** 2
        return loss_yuan / 10000.0

def calculate_loss_cost_rob(minutes):
    """鲁棒模型使用这个"""
    if minutes <= 500:
        return 0.0
    else:
        loss_yuan = 0.2 * (minutes - 500) ** 2
        return loss_yuan / 10000.0

# 这两个函数是相同的!

# 但是! 让我检查distance matrix的使用
print("\n关键问题: 距离矩阵的使用方式")

# 检查两个模型如何获取距离
# 确定性模型: dist.get((wh, store), 0) - 如果缺失，返回0
# 鲁棒模型: dist_matrix.get((wh, c), 99999) - 如果缺失，返回99999

# 但之前诊断显示两个模型的u变量完全相同，所以距离使用应该一致

# ============================================
# 最终诊断: 对比两个模型的实际解决方案
# ============================================
print("\n" + "=" * 70)
print("最终诊断: 检查损耗成本的来源")
print("=" * 70)

# 损耗成本 = Σ loss_cost_matrix[(wh, c)] * qty * u[wh, c]

# 让我计算如果所有需求都由最差仓库服务，损耗成本是多少
max_loss_per_ton = calculate_loss_cost_det(10000)  # 假设最长时间10000分钟
max_total_loss = max_loss_per_ton * total_7d
print(f"\n最大可能损耗成本 (所有需求time=10000): {max_total_loss:.2f} 万元")

# 实际损耗成本
det_loss = 219876
rob_loss = 210562
print(f"确定性模型损耗成本: {det_loss:.2f} 万元")
print(f"鲁棒模型损耗成本: {rob_loss:.2f} 万元")

# 损耗率
det_loss_rate = det_loss / max_total_loss * 100
rob_loss_rate = rob_loss / max_total_loss * 100
print(f"\n确定性模型损耗率: {det_loss_rate:.1f}%")
print(f"鲁棒模型损耗率: {rob_loss_rate:.1f}%")

# ============================================
# 关键发现: 损耗成本差异来自哪里?
# ============================================
print("\n" + "=" * 70)
print("关键发现: 损耗成本差异分析")
print("=" * 70)

loss_diff = det_loss - rob_loss
print(f"损耗成本差异: {loss_diff:.2f} 万元")

# 如果两个模型使用相同的配送策略，损耗成本应该相同
# 损耗成本差异说明配送策略不同

# 可能的原因:
# 1. 开设的仓库不同
# 2. 分配方案不同
# 3. 时效满足率约束不同

# 检查开设仓库
print("\n确定性模型开设的仓库:")
# 从结果文件看，开仓数量是19（包括CDC?)
det_opened = 19
print(f"  总数: {det_opened}")
print(f"  CDC: 2 (必开)")
print(f"  RDC: {det_opened - 2}")

print("\n鲁棒模型开设的仓库:")
rob_opened = 16
print(f"  总数: {rob_opened}")
print(f"  CDC: 2 (必开)")
print(f"  RDC: {rob_opened - 2}")

# ============================================
# 结论: 问题是鲁棒模型可能没有正确约束配送方案
# ============================================
print("\n" + "=" * 70)
print("结论: 问题的根源")
print("=" * 70)

print(f"""
两个模型的关键差异:
1. 开设仓库数: 确定性={det_opened}, 鲁棒={rob_opened}
2. 损耗成本: 确定性={det_loss}万, 鲁棒={rob_loss}万
3. 损耗成本差异: {loss_diff:.2f}万元

可能的根本原因:
1. 鲁棒模型的约束比确定性模型更松，导致它找到了更"激进"的解
2. 鲁棒模型缺少某些关键约束

下一步:
1. 检查鲁棒模型是否满足单源配送约束
2. 检查鲁棒模型是否满足容量约束
3. 检查鲁棒模型是否满足时效约束

如果鲁棒模型Γ=0%的解不满足确定性模型的约束，那说明模型有问题
""")

# ============================================
# 最终验证: 重新计算损耗成本
# ============================================
print("\n" + "=" * 70)
print("最终验证: 损耗成本理论计算")
print("=" * 70)

# 损耗公式: 0.2 * (minutes - 500)^2 / 10000
# 如果minutes > 500

# 检查时间>500分钟的客户数量
long_time_count = 0
short_time_count = 0
long_time_demand = 0
short_time_demand = 0

for c in customer_cities:
    for t in range(T):
        for s in skus:
            if (c, s) not in demand[t]:
                continue
            qty = demand[t][(c, s)]
            # 使用最近仓库的时间
            min_time = min(time_matrix.get((wh, c), 10000) for wh in cdc_names + rdc_names)
            if min_time > 500:
                long_time_count += 1
                long_time_demand += qty
            else:
                short_time_count += 1
                short_time_demand += qty

print(f"短时间可达需求(t<=500): {short_time_demand:.2f}吨, 损耗=0")
print(f"长时间可达需求(t>500): {long_time_demand:.2f}吨, 有损耗")
print(f"总需求: {short_time_demand + long_time_demand:.2f}吨")
