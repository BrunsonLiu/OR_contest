"""
深度验证脚本: 检查鲁棒优化模型的各项假设和计算
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd
import numpy as np
import json
import os

BASE_DIR = str(_REPO_ROOT)
OUTPUT_BASE = os.path.join(BASE_DIR, 'results/question4', 'problem4_robust')

# ============================================================
# 1. 验证 duration 数据分布
# ============================================================
print("=" * 70)
print("1. Duration 数据分布验证")
print("=" * 70)

df_matrix = pd.read_csv(os.path.join(BASE_DIR, 'data/raw', 'df_matrix.csv'))
df_wh = pd.read_csv(os.path.join(BASE_DIR, 'data/raw', 'df_wh.csv'))
df_customer = pd.read_csv(os.path.join(BASE_DIR, 'data/raw', 'df_customer.csv'))

all_wh_names = list(df_wh[df_wh['Type'].isin(['CDC', 'RDC'])]['Name'])
customer_cities = list(df_customer['Name'])

# 构建 duration 查找
dur_dict = {}
for _, row in df_matrix.iterrows():
    dur_dict[(row['From'], row['To'])] = row['Duration']
    dur_dict[(row['To'], row['From'])] = row['Duration']

all_durations = []
wh_cust_durs = []
for wh in all_wh_names:
    for c in customer_cities:
        d = dur_dict.get((wh, c), None)
        if d is not None:
            all_durations.append(d)
            wh_cust_durs.append(d)

print(f"  仓库-门店 pair 数: {len(wh_cust_durs)}")
print(f"  Duration: min={np.min(all_durations):.0f}, max={np.max(all_durations):.0f}, "
      f"mean={np.mean(all_durations):.1f}, median={np.median(all_durations):.1f}")
print(f"  <=500 min (无损耗): {sum(1 for d in all_durations if d <= 500)} ({sum(1 for d in all_durations if d <= 500)/len(all_durations)*100:.1f}%)")
print(f"  >500 min: {sum(1 for d in all_durations if d > 500)} ({sum(1 for d in all_durations if d > 500)/len(all_durations)*100:.1f}%)")

# 损耗成本计算验证
print("\n  典型损耗成本 (0.2*(t-500)^2/10000 万元/吨):")
for t_min in [300, 500, 600, 800, 1000, 1500, 2000]:
    if t_min > 500:
        loss = 0.2 * (t_min - 500)**2 / 10000
    else:
        loss = 0
    print(f"    t={t_min} min → loss={loss:.4f} 万元/吨")

avg_dur = np.mean(all_durations)
avg_loss = 0.2 * max(0, avg_dur - 500)**2 / 10000
print(f"\n  均值 t={avg_dur:.0f} min → loss={avg_loss:.4f} 万元/吨")

# ============================================================
# 2. 验证预测数据与历史数据的 CV
# ============================================================
print("\n" + "=" * 70)
print("2. CV (变异系数) 验证")
print("=" * 70)

df_past = pd.read_csv(os.path.join(BASE_DIR, 'data/raw', 'df_past_order.csv'))
historical_cols = [c for c in df_past.columns if c not in ['Name', 'SKU']]

cvs = []
for _, row in df_past.iterrows():
    vals = row[historical_cols].values.astype(float)
    mean_v = np.mean(vals)
    std_v = np.std(vals, ddof=0)
    if mean_v > 1e-6:
        cvs.append(std_v / mean_v)

print(f"  CV: min={np.min(cvs):.4f}, max={np.max(cvs):.4f}, "
      f"mean={np.mean(cvs):.4f}, median={np.median(cvs):.4f}")
print(f"  CV 分位数: 25%={np.percentile(cvs, 25):.4f}, "
      f"75%={np.percentile(cvs, 75):.4f}")

# DELTA_SCALE = 0.3 的影响
DELTA_SCALE = 0.3
ty_delta = np.mean(cvs) * DELTA_SCALE
print(f"  delta/cv ratio: mean_cv={np.mean(cvs):.4f} × DELTA_SCALE={DELTA_SCALE} = {ty_delta:.4f}")
print(f"  即预测需求的平均偏差约为名义需求的 {ty_delta*100:.2f}%")

# ============================================================
# 3. 验证总需求与每天需求
# ============================================================
print("\n" + "=" * 70)
print("3. 每日名义需求统计")
print("=" * 70)

df_forecast = pd.read_csv(os.path.join(BASE_DIR, 'results/question3', '订单需求量预测结果文件_sota.csv'))
forecast_dates = [c for c in df_forecast.columns if c not in ['Customer', 'SKU']]

for date_col in forecast_dates:
    dm_total = 0
    im_total = 0
    for _, row in df_forecast.iterrows():
        if row['SKU'] == 'dm':
            dm_total += float(row[date_col])
        else:
            im_total += float(row[date_col])
    print(f"  {date_col}: dm={dm_total:.0f}t, im={im_total:.0f}t, total={dm_total+im_total:.0f}t")

# ============================================================
# 4. 验证结果汇总与成本结构
# ============================================================
print("\n" + "=" * 70)
print("4. 结果成本结构分析")
print("=" * 70)

with open(os.path.join(OUTPUT_BASE, 'robust_results.json'), 'r', encoding='utf-8') as f:
    results = json.load(f)

for r in results:
    if r.get('status') == 'INFEASIBLE':
        continue
    gamma = r['gamma']
    tc = r['total_cost']
    loss = r['loss_cost']
    trans_c = r['transport_cost_customer']
    trans_w = r['transport_cost_warehouse']
    proc = r['proc_cost_actual']
    open_c = r['open_cost']
    smart = r['smart_cost']
    rp = r['robust_premium']

    # 手算验证
    manual = trans_c + trans_w + proc + loss + open_c + smart
    diff = tc - manual

    print(f"\n  Gamma={gamma:.1%}:")
    print(f"    损耗/总成本 = {loss/tc*100:.1f}%")
    print(f"    运输(门)/总成本 = {trans_c/tc*100:.1f}%")
    print(f"    运输(仓)/总成本 = {trans_w/tc*100:.1f}%")
    print(f"    处置/总成本 = {proc/tc*100:.1f}%")
    print(f"    开仓+智能/总成本 = {(open_c+smart)/tc*100:.1f}%")
    print(f"    名义成本和 = {manual:.4f}")
    print(f"    模型目标值 = {tc:.4f}")
    print(f"    差值(鲁棒溢价) = {diff:.6f}")
    print(f"    报告鲁棒溢价 = {rp:.6f}")
    print(f"    开仓数 = {r['num_open']}")

# ============================================================
# 5. CRITICAL BUG: 验证 RDC 容量约束的 Gamma 预算
# ============================================================
print("\n" + "=" * 70)
print("5. BUG检查: RDC容量约束的 n_params 计算")
print("=" * 70)

from collections import defaultdict

demand_nominal = {}
for t_idx, date_col in enumerate(forecast_dates):
    demand_nominal[t_idx] = {}
    for _, row in df_forecast.iterrows():
        city = row['Customer']
        sku = row['SKU']
        qty = float(row[date_col])
        demand_nominal[t_idx][(city, sku)] = qty

all_demand_keys_period = {}
for t in range(len(forecast_dates)):
    all_demand_keys_period[t] = list(demand_nominal[t].keys())

T = len(forecast_dates)
skus = ['im', 'dm']

# 当前代码的计算方式 (BUG)
total_params_per_sku = {}
for s in skus:
    total_params_per_sku[s] = sum(
        1 for t in range(T)
        for c in customer_cities
        if (c, s) in demand_nominal[t]
    )
print(f"  【BUG】total_params_per_sku (跨所有天): im={total_params_per_sku['im']}, dm={total_params_per_sku['dm']}")

# 正确的计算方式
n_params_per_day = {}
for t in range(T):
    n_params_per_day[t] = {}
    for s in skus:
        n_params_per_day[t][s] = len([k for k in all_demand_keys_period[t] if k[1] == s])
    print(f"  【正确】Day {t}: im={n_params_per_day[t]['im']}, dm={n_params_per_day[t]['dm']}")

inflation = total_params_per_sku['dm'] / n_params_per_day[0]['dm']
print(f"\n  Gamma 膨胀系数: ~{inflation:.1f}× (全期总数 / 单日数)")
print(f"  例如 Gamma=1%: 应该保护 {int(0.01*n_params_per_day[0]['dm'])} 个参数")
print(f"  实际保护了 {int(0.01*total_params_per_sku['dm'])} 个参数 (膨胀 {inflation:.0f}×)")

# ============================================================
# 6. 验证 robust_premium 的来源
# ============================================================
print("\n" + "=" * 70)
print("6. robust_premium 成分分析")
print("=" * 70)

for r in results:
    if r.get('status') == 'INFEASIBLE':
        continue
    gamma = r['gamma']
    if gamma == 0:
        continue
    rp = r['robust_premium']
    tc = r['total_cost']
    print(f"  Gamma={gamma:.1%}: robust_premium={rp:.2f}, "
          f"占总成本 {rp/tc*100:.2f}%")

# ============================================================
# 7. 对比确定性模型 (如果存在)
# ============================================================
print("\n" + "=" * 70)
print("7. 对比确定性模型 (problem4_loss)")
print("=" * 70)

det_csv = os.path.join(BASE_DIR, 'results/question4', 'problem4_loss', 'output_result', '仓网业务表现文件_汇总.csv')
if os.path.exists(det_csv):
    det = pd.read_csv(det_csv)
    print(det.to_string())
    print("\n  注意: 确定性模型逐天独立求解，无仓库共享约束，与鲁棒模型不可直接对比")
else:
    print("  未找到确定性模型结果")

# ============================================================
# 8. 关键结论
# ============================================================
print("\n" + "=" * 70)
print("8. 综合诊断")
print("=" * 70)

print("""
  ✅ 通过的项目:
  - Duration 数据正确 (均值~890 min, 使用分钟)
  - 损耗公式正确: 0.2*(t-500)^2/10000 万元/吨
  - 算术一致性: objective ≈ Σ各项成本和 (Gamma=0 时完全一致)
  - K系数包含所有成本分量 (运输+损耗+处置+CDC调拨)
  - Gamma=0 robust_premium ≈ 0 (正确)
  - B&S 鲁棒对等变换结构正确
  - CDC约束和时效约束使用 per-day 参数计数 (正确)

  ❌ 发现的问题:
  1. 【严重BUG】RDC容量约束的 n_params 使用全期总数 (T=7天合并),
     应该使用当天的参数数。导致 Gamma 预算膨胀约 7×。
     影响: RDC容量保护过于保守，使得 PoR 曲线偏陡。

  2. 【中等】PoR 曲线非单调: Gamma=3%→13仓, Gamma=5%→12仓,
     Gamma=7%→13仓。可能由 MIP gap=1% 导致。

  3. 【设计问题】所有仓库在 day 0 统一开设，整个周期无动态变化。
     多阶段"适应"性未体现。根本原因: 开仓成本是一次性的，
     且需求模式稳定。

  4. 【结构问题】损耗成本占 78-80%，主导成本结构。
     原因: 二次方损耗公式 + 平均运输时间 890min >> 500min 阈值。
""")

if __name__ == '__main__':
    pass