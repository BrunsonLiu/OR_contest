"""对比确定性 vs 鲁棒的关键差异"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _repo_sys
_repo_sys.path.insert(0, str(_REPO_ROOT))
import pandas as pd, numpy as np, os

BASE = str(_REPO_ROOT)
loss_out = f'{BASE}/results/question4/problem4_loss/output_result'

# 读确定性模型每天的供应关系
dm = {}
for day_file in sorted([f for f in os.listdir(loss_out) if '仓网供应关系' in f]):
    df = pd.read_csv(f'{loss_out}/{day_file}')
    day = day_file.split('_')[-1].replace('.csv','')
    dm[day] = df

print("=" * 70)
print("确定性模型: 每天 CDC→RDC 的 RDC 数量")
total_unique_rdc = set()
for day, df in sorted(dm.items()):
    rdcs = set(df['服务对象'] if '服务对象' in df.columns else df.iloc[:,1])
    # 只看RDC (排除CDC)
    rdc_only = {r for r in rdcs if 'DC' in str(r) and 'CDC' not in str(r)}
    total_unique_rdc.update(rdc_only)
    print(f"  {day}: {len(rdc_only)} RDCs — {sorted(rdc_only)[:8]}...")

print(f"\n  7天合计唯一RDC: {len(total_unique_rdc)} 个")
print(f"  {sorted(total_unique_rdc)}")

# 读df_matrix
df_mat = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
dur = {}
for _, r in df_mat.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']

# 计算CDC到RDC的平均时长
print("\n" + "=" * 70)
print("CDC→RDC 时长统计")
nk = 'gang-kou-CDC' if 'gang-kou-CDC' in [r['From'] for _,r in df_mat.iterrows()] else 'guang-zhou-CDC'
for cdc_name in [nk, 'nei-lu-CDC']:
    durations = []
    for rdc in sorted(total_unique_rdc):
        d = dur.get((cdc_name, rdc))
        if d:
            durations.append(d)
    if durations:
        loss_per_ton = [0.2*(d-500)**2/10000 if d>500 else 0 for d in durations]
        print(f"  {cdc_name} → {len(durations)} RDCs:")
        print(f"    时长: mean={np.mean(durations):.0f}, min={np.min(durations)}, max={np.max(durations)}")
        print(f"    损耗(万/吨): mean={np.mean(loss_per_ton):.2f}, max={np.max(loss_per_ton):.2f}")
        print(f"    总损耗(仅CDC侧): sum = {sum(loss_per_ton):.0f} 万/吨")

# 对比鲁棒模型用了哪些RDC
print("\n" + "=" * 70)
print("鲁棒模型 Γ=0% 选的仓库")
import json
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json','r',encoding='utf-8') as f:
    rob = json.load(f)
r0 = rob[0]
rob_rdc = set(r0['warehouses'])
print(f"  {len(rob_rdc)} RDCs: {sorted(rob_rdc)}")
print(f"  确定多但鲁棒没有的: {sorted(total_unique_rdc - rob_rdc)}")