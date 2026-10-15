"""
精确对比: 鲁棒模型与确定性模型的timeliness约束
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
# 关键分析: v约束的数学等价性
# ============================================
print("=" * 70)
print("关键分析: v约束的数学等价性")
print("=" * 70)

print("""
确定性模型v约束分析:
对于每个(wh, c, s)：
- 如果 t(wh,c) <= 600: 添加约束 v + u >= 1  (即 u - v <= 0)
- 如果 t(wh,c) > 600:  添加约束 v + u <= 1

由于单源约束 Σ u = 1:
- 只有一个wh的u=1，其他都是0
- v的值由服务这个需求的wh决定

因此，定性模型中v的约束可以简化为：
- v = 1 如果 t(wh,c) <= 600 (即被快速仓库服务)
- v = 0 如果 t(wh,c) > 600 (即被慢速仓库服务)


鲁棒模型v约束分析:
对于每个(c, s):
- v <= Σ_{wh: t(wh,c) <= 600} u
- v是二进制

结论：两个模型的v约束是**数学等价**的！
""")

# ============================================
# 真正的问题: 检查代码实现
# ============================================
print("\n" + "=" * 70)
print("真正的问题: 检查代码实现")
print("=" * 70)

# 检查鲁棒模型中travel_time_matrix的定义
print("\n鲁棒模型travel_time_matrix定义:")
print("  travel_time_matrix[(wh, c)] = dur_matrix.get((wh, c), 10000)")
print("  其中dur_matrix是双向的")

# 检查确定性模型中time_matrix的定义
print("\n确定性模型time_matrix定义:")
print("  time_matrix = {(row['From'], row['To']): row['Duration'] for _, row in df_matrix.iterrows()}")
print("  这是单向的!")

# 这是一个潜在问题!
print("\n" + "=" * 70)
print("潜在问题: 距离矩阵的方向性")
print("=" * 70)

# 检查df_matrix中From和To的关系
print("\ndf_matrix结构:")
print(f"  总行数: {len(df_matrix)}")
print(f"  From列唯一值数: {df_matrix['From'].nunique()}")
print(f"  To列唯一值数: {df_matrix['To'].nunique()}")

# 检查From是什么类型
from_values = df_matrix['From'].unique()
print(f"\nFrom列值的类型:")
from_wh = [v for v in from_values if v in all_wh_names]
from_cust = [v for v in from_values if v in customer_cities]
print(f"  仓库: {len(from_wh)}个")
print(f"  客户: {len(from_cust)}个")

to_values = df_matrix['To'].unique()
print(f"\nTo列值的类型:")
to_wh = [v for v in to_values if v in all_wh_names]
to_cust = [v for v in to_values if v in customer_cities]
print(f"  仓库: {len(to_wh)}个")
print(f"  客户: {len(to_cust)}个")

# 关键问题: df_matrix是单向还是双向?
print("\n关键问题: df_matrix是单向还是双向?")

# 检查(warehouse, customer)是否有正向和反向条目
fwd_count = 0
rev_count = 0
for wh in all_wh_names:
    for c in customer_cities:
        if (wh, c) in dur_matrix:
            fwd_count += 1
        if (c, wh) in dur_matrix:
            rev_count += 1

print(f"  (wh, customer)正向条目: {fwd_count}")
print(f"  (customer, wh)反向条目: {rev_count}")

if fwd_count > 0 and rev_count > 0:
    print("\n  结论: df_matrix是双向的!")
elif fwd_count > 0 and rev_count == 0:
    print("\n  结论: df_matrix是单向的(仅wh->customer)!")
elif fwd_count == 0 and rev_count > 0:
    print("\n  结论: df_matrix是单向的(仅customer->wh)!")
else:
    print("\n  结论: 两者都没有?!?")

# ============================================
# 真正的问题: 检查代码中的travel_time_matrix
# ============================================
print("\n" + "=" * 70)
print("真正的问题: travel_time_matrix的构建")
print("=" * 70)

print("""
从solve_problem4_robust.py (line 235-238):
for wh_name in all_wh_names:
    for c_city in customer_cities:
        travel_time_matrix[(wh_name, c_city)] = dur_matrix.get((wh_name, c_city), 10000)

这里travel_time_matrix[(wh, c)]直接从dur_matrix获取。
dur_matrix在line 101-108被构建为对称矩阵。
""")

# 验证dur_matrix确实是对称的
print("\n验证dur_matrix的对称性:")
asym_count = 0
for (f, t), d in [(k, v) for k, v in dur_matrix.items() if k[0] in all_wh_names and k[1] in customer_cities]:
    rev_d = dur_matrix.get((t, f), None)
    if rev_d is not None and abs(d - rev_d) > 0.001:
        asym_count += 1
        if asym_count <= 3:
            print(f"  非对称: ({f}, {t}) = {d}, ({t}, {f}) = {rev_d}")

if asym_count == 0:
    print("  所有条目都是对称的!")
else:
    print(f"  非对称条目数: {asym_count}")

# ============================================
# 最终分析: 约束差异的来源
# ============================================
print("\n" + "=" * 70)
print("最终分析: 约束差异的来源")
print("=" * 70)

print("""
既然timeliness约束是数学等价的，问题可能出在其他地方。

让我检查一下两个模型之间的约束数量差异:

1. service_open约束:
   - 确定性模型: 27,132 (每个u变量一个)
   - 鲁棒模型: 25,704 (只有RDC的u变量)
   - 差异: 1,428

2. timeliness约束:
   - 确定性模型: 27,132 (每个u变量)
   - 鲁棒模型: 1,428 (每个(c,s)对)
   - 差异: 25,704

3. w_constraint:
   - 确定性模型: 280 (CDC+RDC)
   - 鲁棒模型: 252 (仅RDC)
   - 差异: 28

总差异: 27,160

最大的差异在timeliness约束!
虽然数学上等价，但约束数量差异很大。

让我检查是否有timeliness约束被遗漏...
""")

# ============================================
# 检查: 鲁棒模型是否对所有(c,s)都添加了v约束
# ============================================
print("\n" + "=" * 70)
print("检查: 鲁棒模型v约束的覆盖范围")
print("=" * 70)

total_demand_keys = sum(len(demand[t]) for t in range(T))
print(f"总需求对数 (所有周期): {total_demand_keys}")
print(f"每周期需求对数: {len(demand[0])}")
print(f"周期数: {T}")

# 检查有多少(c,s)对在travel_time_matrix中有快速仓库
has_fast_count = 0
no_fast_count = 0
for t in range(T):
    for (c, s) in demand[t]:
        has_fast = False
        eligible = [sku_cdc[s]] + rdc_names
        for wh in eligible:
            tt = dur_matrix.get((wh, c), 10000)
            if tt <= TIMELINESS_THRESHOLD:
                has_fast = True
                break
        if has_fast:
            has_fast_count += 1
        else:
            no_fast_count += 1

print(f"\n有快速仓库可达的需求对数: {has_fast_count}")
print(f"无快速仓库可达的需求对数: {no_fast_count}")

# 这意味着鲁棒模型只对has_fast_count个(c,s,t)添加v约束
# 对no_fast_count个(c,s,t)，v只能是0

# ============================================
# 结论
# ============================================
print("\n" + "=" * 70)
print("结论")
print("=" * 70)

print(f"""
经过详细分析，timeliness约束在数学上是等价的。

那问题出在哪里?

让我重新审视LP relaxation的差异来源...

关键发现:
- 鲁棒模型Γ=0% LP relaxation: 224,312
- 确定性模型LP relaxation: 232,543
- 差异: 8,231万元

这个差异相当于:
- 约 8,231 / 86,345 = 9.5% 的总需求量的超时损耗

可能的原因:
1. 某个约束被错误地添加或遗漏
2. 目标函数系数设置错误
3. 数据处理不一致

下一步:
1. 逐行对比两个模型的目标函数系数
2. 检查是否有遗漏的约束
3. 或者重新实现鲁棒模型，确保与确定性模型完全等价
""")
