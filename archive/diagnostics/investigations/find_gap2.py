"""
终极验证：用鲁棒模型的解，分别用两个模型的公式计算成本
找出公式差异
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import json
import pandas as pd
import numpy as np

BASE = str(_REPO_ROOT)

df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')

dist = {}
dur = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

proc_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

loss_cost_matrix = {(f, t): loss_per_ton(d) for (f, t), d in dur.items()}

# 读取鲁棒模型的详细结果
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json', 'r', encoding='utf-8') as f:
    rob = json.load(f)

r0 = rob[0]
daily = r0['daily_costs']

print("=" * 70)
print("鲁棒模型 Γ=0% 报告的成本 vs 用确定性模型公式重算")
print("=" * 70)

# 鲁棒模型报告
print(f"\n鲁棒模型报告:")
print(f"  运输(门): {r0['transport_cost_customer']:.2f}")
print(f"  运输(仓): {r0['transport_cost_warehouse']:.2f}")
print(f"  处置费:   {r0['proc_cost_actual']:.2f}")
print(f"  损耗:     {r0['loss_cost']:.2f}")
print(f"  开仓费:   {r0['open_cost']:.2f}")
print(f"  智能费:   {r0['smart_cost']:.2f}")
print(f"  总成本:   {r0['total_cost']:.2f}")

# 从 daily_costs 汇总
sum_trans_cust = sum(d['transport_cust'] for d in daily)
sum_trans_wh = sum(d['transport_wh'] for d in daily)
sum_proc = sum(d['proc'] for d in daily)

print(f"\n从daily_costs汇总:")
print(f"  运输(门): {sum_trans_cust:.2f}")
print(f"  运输(仓): {sum_trans_wh:.2f}")
print(f"  处置费:   {sum_proc:.2f}")

# 检查鲁棒模型的处置费计算
# 鲁棒模型: proc = 2 * proc_cost * qty (对u变量)
# 但智能系统折扣: w变量 obj = -0.8 * proc_cost (连续变量)
# 确定性模型: proc = 2 * proc_cost * qty (对u变量)
# 智能系统折扣: w变量 obj = 1.5 - 0.8 * proc_cost (二值变量)

# 关键差异1: 确定性模型的w变量是二值，obj = 1.5 - 0.8*proc_cost
#   采购智能系统: 付1.5万 + 省0.8*proc_cost*处理量
# 鲁棒模型的w变量是连续，表示处理量
#   w的obj = -0.8*proc_cost (每吨省0.8*proc_cost)
#   z变量的obj = 1.5 (采购费)

print("\n" + "=" * 70)
print("关键差异分析")
print("=" * 70)

print("""
  确定性模型:
    w变量: Binary, obj = 1.5 - 0.8 × proc_cost
    含义: w=1表示采购智能系统，付1.5万，省0.8×proc_cost
    问题: 0.8×proc_cost 是固定的折扣，不随处理量变化！
    
  鲁棒模型:
    z变量: Binary, obj = 1.5 (采购决策)
    w变量: Continuous, obj = -0.8 × proc_cost (每吨折扣)
    含义: w = 实际使用智能系统处理的吨数
    约束: w ≤ z × cap (只有采购了才能用)
    约束: w ≤ 实际出库量 (不能超过处理量)
""")

# 检查确定性模型的w变量obj
# 如果 proc_cost = 0.007, 则 0.8 × 0.007 = 0.0056
# obj = 1.5 - 0.0056 = 1.4944
# 这意味着采购智能系统的净成本 = 1.4944 万/仓
# 但实际应该省 0.8 × 0.007 × 处理量

# 计算一个典型RDC的处理量
for wh in ['nan-jing-DC', 'wu-han-DC', 'guang-zhou-DC']:
    pc = proc_cost.get(wh, 0)
    print(f"  {wh}: proc_cost={pc}, 0.8×proc_cost={0.8*pc:.4f}")
    print(f"    确定性模型w obj = 1.5 - {0.8*pc:.4f} = {1.5-0.8*pc:.4f}")
    print(f"    如果处理1000吨: 实际应省 {0.8*pc*1000:.2f} 万, 但确定性模型只省 {0.8*pc:.4f} 万")
    print(f"    差异: {0.8*pc*1000 - 0.8*pc:.2f} 万/仓/7天")

# ========== 最关键的检查 ==========
print("\n" + "=" * 70)
print("最关键: 确定性模型的处置费是否重复计算了？")
print("=" * 70)

print("""
  确定性模型 u变量 obj = 运输 + 损耗 + 2×proc_cost×qty
  → 每吨货的处置费 = 2 × proc_cost (入库+出库)
  
  鲁棒模型 u变量 obj = 运输 + 损耗 + 2×proc_cost×qty  
  → 同上
  
  但智能系统折扣:
  确定性: w obj = 1.5 - 0.8×proc_cost (固定值，不乘qty!)
  鲁棒:   w obj = -0.8×proc_cost (每吨), z obj = 1.5 (固定)
  
  如果一个仓库处理 1000 吨:
  确定性模型折扣: 0.8 × proc_cost (只省一次!)
  鲁棒模型折扣: 0.8 × proc_cost × 1000 (每吨都省!)
  
  这就是差距的来源！
""")

# 验证
total_proc_reported = r0['proc_cost_actual']
total_smart_discount = sum(d.get('discount', 0) for d in daily)
print(f"  鲁棒模型报告处置费: {total_proc_reported:.2f}")
print(f"  鲁棒模型智能折扣: {total_smart_discount:.2f}")

# 计算确定性模型如果用同样的解，智能折扣应该是多少
# 确定性模型: 每个采购智能系统的仓库省 0.8 × proc_cost (固定)
# 鲁棒模型: 每吨省 0.8 × proc_cost × 吨数
print(f"\n  如果用确定性模型的w公式(固定折扣):")
for wh in r0['open_warehouses']:
    pc = proc_cost.get(wh, 0)
    print(f"    {wh}: 确定性折扣={0.8*pc:.4f}万, 鲁棒折扣={0.8*pc*1000:.2f}万(假设1000吨)")
