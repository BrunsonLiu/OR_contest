"""最终定位: 确定性模型 vs 鲁棒模型的目标函数差异"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd, numpy as np

BASE = str(_REPO_ROOT)
df_proc = pd.read_csv(f'{BASE}/data/raw/df_proc.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')

proc_cost = {}
for _, row in df_proc.iterrows():
    proc_cost[row['Name']] = row['Processing_fee']

dist = {}
for _, r in df_matrix.iterrows():
    dist[(r['From'], r['To'])] = r['Distance']
    dist[(r['To'], r['From'])] = r['Distance']

# 确定性模型的损耗函数
with open(f'{BASE}/src/solvers/question4/solve_problem4_loss.py', 'r', encoding='utf-8') as f:
    det_code = f.read()

import re
loss_func = re.search(r'def calculate_loss_cost.*?(?=\ndef |\Z)', det_code, re.DOTALL)
if loss_func:
    print("确定性模型的损耗函数:")
    for line in loss_func.group(0).split('\n')[:15]:
        print(f"  {line}")

# 检查: 确定性模型的u变量obj是否乘了qty
u_obj_lines = [l.strip() for l in det_code.split('\n') if 'obj' in l.lower() and 'u_' in l and 'add' not in l]
print("\n确定性模型 u 变量 obj 计算:")
for l in u_obj_lines[:10]:
    print(f"  {l}")

# 检查: 确定性模型的f变量obj
f_obj_lines = [l.strip() for l in det_code.split('\n') if 'obj' in l.lower() and 'f_' in l and 'add' not in l and 'var_f' in l]
print("\n确定性模型 f 变量 obj 计算:")
for l in f_obj_lines[:10]:
    print(f"  {l}")

# 关键检查: 确定性模型的损耗阈值
print("\n" + "=" * 70)
print("关键: 损耗阈值")
print("=" * 70)
if '600' in loss_func.group(0):
    print("  🔴 确定性模型损耗阈值 = 600!")
    print("  题目要求: 0.2×(t-500)² → 阈值应该是500!")
    print("  这就是差距的根源!")
elif '500' in loss_func.group(0):
    print("  ✅ 确定性模型损耗阈值 = 500")

# 验证: 如果阈值从500改成600,损耗变化多少
def loss_500(t): return 0.0 if t<=500 else 0.2*(t-500)**2/10000
def loss_600(t): return 0.0 if t<=600 else 0.2*(t-600)**2/10000

# 用典型运输时间计算
print("\n典型运输时间下的损耗差异:")
for t in [600, 700, 800, 900, 1000, 1200, 1500, 2000]:
    l500 = loss_500(t)
    l600 = loss_600(t)
    print(f"  t={t}min: loss(500)={l500:.4f}, loss(600)={l600:.4f}, 差={l500-l600:.4f} 万/吨")

# 估算总影响
# 假设平均运输时间700min, 总量86000吨
avg_diff = loss_500(700) - loss_600(700)
total_impact = avg_diff * 86000 * 7  # 7天
print(f"\n如果平均700min, 86000吨/天, 7天:")
print(f"  每吨差异: {avg_diff:.4f} 万")
print(f"  总差异: {total_impact:.0f} 万")
print(f"  实际差距: 233950 - 79807 = {233950-79807} 万")
