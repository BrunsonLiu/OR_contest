"""
读取并对比两个模型的详细结果
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
import json

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_DIR = str(_REPO_ROOT)

# ============================================
# 读取确定性模型结果
# ============================================
print("=" * 70)
print("确定性模型结果")
print("=" * 70)

det_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss_v2', 'output_result', '仓网业务表现文件_汇总.csv')
if os.path.exists(det_file):
    df_det = pd.read_csv(det_file)
    print(df_det.to_string())
    print(f"\n列名: {df_det.columns.tolist()}")

# ============================================
# 读取鲁棒模型结果
# ============================================
print("\n" + "=" * 70)
print("鲁棒模型结果")
print("=" * 70)

robust_file = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust', 'robust_results.json')
if os.path.exists(robust_file):
    with open(robust_file, 'r') as f:
        robust_results = json.load(f)

    for r in robust_results:
        if abs(r['gamma'] - 0.0) < 0.001:
            print(f"Γ={r['gamma']:.1%}:")
            print(f"  总成本: {r['total_cost']:.2f}")
            if 'cost_breakdown' in r:
                for k, v in r['cost_breakdown'].items():
                    print(f"    {k}: {v:.2f}")
            break

# ============================================
# 读取鲁棒模型详细输出
# ============================================
print("\n" + "=" * 70)
print("鲁棒模型详细结果 (period 0)")
print("=" * 70)

robust_detail_dir = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust')
if os.path.exists(robust_detail_dir):
    for gamma_dir in os.listdir(robust_detail_dir):
        if 'gamma_0' in gamma_dir.lower() or gamma_dir == 'gamma_0.00' or gamma_dir == 'gamma_0.0':
            detail_file = os.path.join(robust_detail_dir, gamma_dir, '仓网业务表现文件_汇总.csv')
            if os.path.exists(detail_file):
                df_rob = pd.read_csv(detail_file)
                print(df_rob.to_string())
                break

# ============================================
# 核心诊断: 对比两套代码的关键差异
# ============================================
print("\n" + "=" * 70)
print("核心诊断: 两个模型的精确对比")
print("=" * 70)

print("""
根据之前的分析，两个模型的关键差异在于：

1. u变量:
   - 确定性模型: 无距离过滤
   - 鲁棒模型: dist > 5000km 过滤
   - 但实际差异: 0个变量

2. z/w变量:
   - 确定性模型: CDC + RDC
   - 鲁棒模型: 仅 RDC
   - 影响: 确定性模型可以购买CDC智能系统获得折扣

3. service_open约束:
   - 确定性模型: 所有u变量都有
   - 鲁棒模型: 仅RDC的u变量有
   - 影响: CDC的u变量不受约束限制

4. 目标系数:
   - 两个模型的u变量目标系数相同
   - 但鲁棒模型缺少CDC的w折扣

5. 约束数量:
   - 确定性模型: 56859个约束
   - 鲁棒模型: 29463个约束
   - 差异: 27396个约束

关键问题: 为什么约束数量差异这么大，但gap只有8,827万?
""")

# ============================================
# 检查: 重新运行鲁棒模型Γ=0%
# ============================================
print("\n" + "=" * 70)
print("验证: 重新运行鲁棒模型Γ=0%")
print("=" * 70)

# 让我检查鲁棒模型的输出目录结构
print("\n鲁棒模型输出目录结构:")
if os.path.exists(robust_detail_dir):
    for item in os.listdir(robust_detail_dir):
        item_path = os.path.join(robust_detail_dir, item)
        if os.path.isdir(item_path):
            files = os.listdir(item_path)
            print(f"  {item}/: {files[:5]}...")

# ============================================
# 真正的问题: 两个模型使用的数据源不同
# ============================================
print("\n" + "=" * 70)
print("真正的问题: 检查数据源")
print("=" * 70)

# 检查确定性模型使用的数据
df_forecast_det = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))
print(f"\n预测数据形状: {df_forecast_det.shape}")
print(f"预测数据列: {df_forecast_det.columns.tolist()}")
print(f"预测数据行数: {len(df_forecast_det)}")
print(f"前5行:")
print(df_forecast_det.head())

# 检查需求数据的唯一值
print(f"\nCustomer唯一值: {df_forecast_det['Customer'].nunique()}")
print(f"SKU唯一值: {df_forecast_det['SKU'].unique()}")

# ============================================
# 结论: 问题可能在鲁棒模型的某个bug
# ============================================
print("\n" + "=" * 70)
print("结论: 需要在鲁棒模型Γ=0%时打印详细约束信息")
print("=" * 70)

print("""
下一步:
1. 修改鲁棒模型，在Γ=0%时打印约束信息
2. 与确定性模型的约束进行逐行对比
3. 找出具体哪个约束不同

或者:

直接修复已知的差异:
1. 添加CDC的z/w变量到鲁棒模型
2. 确保service_open约束包含CDC的u变量
""")

# ============================================
# 直接修复: 添加CDC z/w到鲁棒模型
# ============================================
print("\n" + "=" * 70)
print("直接修复方案")
print("=" * 70)

print("""
修复1: 添加CDC的z变量
修复2: 添加CDC的w变量
修复3: 添加CDC u的service_open约束

但这可能不会解决gap问题，因为CDC智能系统只能节省约475万

真正的问题可能在于约束的数学形式
""")

# ============================================
# 关键发现: 让我检查鲁棒模型的timeliness约束
# ============================================
print("\n" + "=" * 70)
print("关键发现: 检查鲁棒模型的timeliness约束")
print("=" * 70)

# 读取鲁棒模型代码
with open(os.path.join(BASE_DIR, 'src/solvers/question4/solve_problem4_robust.py'), 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("\n鲁棒模型timeliness v约束 (line 601-622):")
for i in range(600, 623):
    if i < len(lines):
        print(f"  {i+1}: {lines[i]}", end='')

print("\n鲁棒模型timeliness overall约束 (line 624-638):")
for i in range(623, 639):
    if i < len(lines):
        print(f"  {i+1}: {lines[i]}", end='')

print("""
问题: 鲁棒模型使用 compute_worst_case_total_demand 计算worst_total
但这个worst_total在timeliness overall约束中使用，而不在CDC容量约束中使用！

而在确定性模型中，timeliness约束使用的是实际需求量，不是worst-case需求量

这是一个关键差异！
""")
