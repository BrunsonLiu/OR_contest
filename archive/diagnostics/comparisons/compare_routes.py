"""对比确定性模型 vs 鲁棒模型的路由选择差异"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import json

BASE = str(_REPO_ROOT)

df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_forecast = pd.read_csv(f'{BASE}/results/question3/订单需求量预测结果文件_sota.csv')

# 构建 duration 矩阵
dur = {}
for _, r in df_matrix.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]

# 读鲁棒模型（Gamma=0%）第一天的分配结果
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json', 'r', encoding='utf-8') as f:
    robust = json.load(f)

r0 = robust[0]  # Gamma=0%
daily = r0['daily_costs']

print("=" * 70)
print("鲁棒模型 Γ=0% 每天平均运输时长")
print("=" * 70)

for d in daily:
    day = d['day']
    routes = d.get('routes', [])
    durations = []
    for rt in routes:
        wh = rt['warehouse']
        c = rt['customer']
        s = rt['sku']
        qty = rt['qty']
        d_val = dur.get((wh, c), dur.get((c, wh)))
        if d_val:
            durations.extend([d_val] * int(qty))
    if durations:
        avg = np.mean(durations)
        print(f"  Day {day} ({forecast_dates[day]}): {len(set(str(r) for r in routes))} routes, "
              f"avg duration = {avg:.0f} min, max = {np.max(durations):.0f}")

print("\n" + "=" * 70)
print("总体统计")
print("=" * 70)
all_durs = []
for d in daily:
    routes = d.get('routes', [])
    for rt in routes:
        d_val = dur.get((rt['warehouse'], rt['customer']), dur.get((rt['customer'], rt['warehouse'])))
        if d_val:
            all_durs.extend([d_val] * int(rt['qty']))
print(f"  加权平均运输时长: {np.mean(all_durs):.0f} min")
print(f"  中位数: {np.median(all_durs):.0f} min")
print(f"  <=500min (无损): {sum(1 for d in all_durs if d <= 500)/len(all_durs)*100:.1f}%")
print(f"  500-1000min: {sum(1 for d in all_durs if 500 < d <= 1000)/len(all_durs)*100:.1f}%")
print(f"  >1000min: {sum(1 for d in all_durs if d > 1000)/len(all_durs)*100:.1f}%")

# 理论损耗验证
avg_loss_per_ton = sum(
    max(0, 0.2 * (d - 500)**2 / 10000) for d in all_durs
) / len(all_durs) if all_durs else 0
total_ton = sum(sum(rt['qty'] for rt in d.get('routes', [])) for d in daily)
theo_loss = avg_loss_per_ton * total_ton
print(f"\n  理论损耗: {theo_loss:.0f} 万元 (vs 报告: {r0['loss_cost']:.0f})")
print(f"  理论每吨损耗: {avg_loss_per_ton:.4f} 万元/吨")

# 检查是不是 dist.get 默认0导致的问题
print("\n" + "=" * 70)
print("距离矩阵覆盖检查")
print("=" * 70)
all_wh = [r['From'] for _, r in df_matrix.iterrows()] + [r['To'] for _, r in df_matrix.iterrows()]
all_wh_unique = list(set(all_wh))
all_cust = list(set(df_forecast['Customer']))
print(f"  矩阵中仓库数: {len([w for w in all_wh_unique if 'DC' in w or 'CDC' in w])}")
print(f"  矩阵中城市数: {len([w for w in all_wh_unique if w not in [x for x in all_wh_unique if 'DC' in x or 'CDC' in x]])}")
missing = 0
for wh in all_wh_unique:
    if 'DC' not in wh and 'CDC' not in wh:
        continue
    for c in all_cust:
        if (wh, c) not in dur:
            missing += 1
print(f"  缺失的 warehouse-customer 对数: {missing}")
if missing > 0:
    print(f"  缺少的配对在确定性模型中被当成 dist=0, loss=0 处理!")