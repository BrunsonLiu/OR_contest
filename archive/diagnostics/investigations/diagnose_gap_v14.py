"""
深入分析: timeliness约束的差异
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

cdc_names = list(df_wh[df_wh['Type'] == 'CDC']['Name'])
rdc_names = list(df_wh[df_wh['Type'] == 'RDC']['Name'])
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]
all_wh_names = cdc_names + rdc_names
customer_cities = list(df_customer['Name'])
skus = ['im', 'dm']

# 时间矩阵
dur_matrix = {}
for _, row in df_matrix.iterrows():
    dur_matrix[(row['From'], row['To'])] = row['Duration']
    dur_matrix[(row['To'], row['From'])] = row['Duration']

TIMELINESS_THRESHOLD = 600

# ============================================
# 关键发现: v变量的语义差异
# ============================================
print("=" * 70)
print("关键发现: v变量的语义差异")
print("=" * 70)

print("""
确定性模型v约束 (line 377-395):
---------------------------------
对于每个(wh, store, sku):

如果 travel_time(wh, store) <= 600:
    v + u >= 1 (即 u - v <= 0)
    含义: 如果wh服务store，则v必须为1

如果 travel_time(wh, store) > 600:
    v + u <= 1
    含义: 如果wh服务store，则v必须为0

结合单源约束 Σ u = 1:
- 如果有一个wh的travel_time <= 600，则v = 1
- 如果所有wh的travel_time > 600，则v = 0


鲁棒模型v约束 (line 601-622):
---------------------------------
对于每个(store, sku):

v <= Σ_{wh: time<=600} u
含义: v不能超过可以被快速服务的量

整体时效约束 (line 624-638):
Σ v * qty >= 0.95 * Σ demand
""")

# ============================================
# 检查: 有多少(wh, store)对的travel_time <= 600?
# ============================================
print("\n" + "=" * 70)
print("检查: travel_time <= 600 的(wh, store)对数量")
print("=" * 70)

fast_count = 0
slow_count = 0
for wh in all_wh_names:
    for c in customer_cities:
        t = dur_matrix.get((wh, c), 10000)
        if t <= TIMELINESS_THRESHOLD:
            fast_count += 1
        else:
            slow_count += 1

total = fast_count + slow_count
print(f"快速(t<=600): {fast_count} ({fast_count/total*100:.1f}%)")
print(f"慢速(t>600): {slow_count} ({slow_count/total*100:.1f}%)")

# ============================================
# 关键问题: 约束形式的数学差异
# ============================================
print("\n" + "=" * 70)
print("关键问题: 约束形式的数学差异")
print("=" * 70)

print("""
关键差异:

确定性模型中，对于每个(wh, c, s):
- 如果 t(wh,c) <= 600: u - v <= 0  →  v >= u
- 如果 t(wh,c) > 600:  u + v <= 1  →  v <= 1 - u

鲁棒模型中，对于每个(c, s):
- v <= Σ_{wh: t<=600} u

假设有一个需求(c,s)可以被3个仓库服务，其中2个快速，1个慢速。

确定性模型约束:
- 快速仓库1: v >= u1
- 快速仓库2: v >= u2
- 慢速仓库:  v <= 1 - u3

结合单源约束 u1 + u2 + u3 = 1:
- 如果u1=1: v >= 1, v <= 0 (矛盾!)

等等，我重新理解一下...

确定性模型中，当travel_time > 600时，约束是u + v <= 1。
这意味着如果u = 1，则v <= 0。
但v是二进制变量，所以v = 0。

所以确定性模型实际上强制:
- 如果某个仓库服务某个需求，且该仓库慢速，则v = 0

而v最终会被整体时效约束约束: Σ v * qty >= 0.95 * Σ demand

这意味着:
- 如果某个需求只能由慢速仓库服务，则v = 0，该需求不计入满足时效的需求
- 整体时效约束要求至少95%的需求满足时效

在鲁棒模型中:
- v <= Σ u_fast
- 如果某个需求由慢速仓库服务，v <= 0，所以v = 0
- 如果某个需求由快速仓库服务，v <= 1，所以v可以是1

这部分是相同的!

但关键差异在于:
确定性模型: v是独立的，由每个仓库的配送决定
鲁棒模型: v <= Σ u_fast，所有快速仓库共同决定v

这个差异可能导致不同的解!
""")

# ============================================
# 具体例子: 约束的差异
# ============================================
print("\n" + "=" * 70)
print("具体例子: 约束的差异")
print("=" * 70)

# 找一个有多个快速仓库的客户
example_c = None
example_s = 'im'
fast_whs = []
for wh in [port_cdc] + rdc_names:  # 对于im，从port_cdc或RDC服务
    t = dur_matrix.get((wh, None), 10000)
    # 找一个有多个快速仓库的客户
    for c in customer_cities:
        t = dur_matrix.get((wh, c), 10000)
        if t <= TIMELINESS_THRESHOLD:
            if c not in [x[0] for x in fast_whs]:
                fast_whs.append((c, wh, t))

if fast_whs:
    # 找一个有多个快速仓库的客户
    from collections import Counter
    c_counts = Counter([x[0] for x in fast_whs])
    multi_fast_c = [c for c, cnt in c_counts.items() if cnt >= 2]
    if multi_fast_c:
        c = multi_fast_c[0]
        example_c = c
        print(f"\n示例客户: {c} ({example_s})")
        for wh in [port_cdc] + rdc_names:
            t = dur_matrix.get((wh, c), 10000)
            status = "快速" if t <= TIMELINESS_THRESHOLD else "慢速"
            print(f"  {wh}: 时间={t}分钟, {status}")

print("""
在这个例子中:
- 如果只分配给快速仓库1: 确定性v >= 1, 鲁棒v <= 1 → v都可以是1
- 如果分配给快速仓库1和2: 确定性v >= max(u1,u2), 鲁棒v <= u1+u2 → v都可以是1

所以对于单一分配，两者应该没有区别...

但问题可能在于:
1. 多个快速仓库可以"共享"满足时效的贡献
2. 确定性模型更严格地限制了v的值

让我重新检查约束...

实际上，我认为问题出在鲁棒模型的v约束可能不够严格!
""")

# ============================================
# 最终结论
# ============================================
print("\n" + "=" * 70)
print("最终结论")
print("=" * 70)

print(f"""
根本原因: 鲁棒模型Γ=0%的LP relaxation ({224311.88}) < 确定性模型LP relaxation ({232543.43})

差异: {224311.88 - 232543.43:.2f} ≈ 8,231万元

这意味着:
1. 鲁棒模型的可行域比确定性模型更宽松
2. 鲁棒模型可以找到"更好"(更低成本)但可能违反确定性模型约束的解

可能的问题来源:
1. **timeliness约束的形式差异** - 最可能的原因
   - 确定性模型: 对每个(wh,c,s)添加约束
   - 鲁棒模型: 对每个(c,s)添加约束 v <= Σ u_fast
   
2. **v变量的语义不同**
   - 确定性模型: v是"每个(wh,c,s)的时效满足标志"
   - 鲁棒模型: v是"每个(c,s)的时效满足标志"
   
3. **鲁棒模型缺少某些timeliness约束**

修复建议:
1. 检查鲁棒模型的timeliness约束是否正确
2. 确保Γ=0%时两个模型的约束完全等价
3. 可能需要修改鲁棒模型的timeliness约束形式
""")
