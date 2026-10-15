"""
可视化：确定性模型 vs 鲁棒模型的仓库选址对比
在地图上展示 CDC→RDC→门店 的两层运输结构
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import json

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE = str(_REPO_ROOT)

df_wh = pd.read_csv(f'{BASE}/data/raw/df_wh.csv')
df_matrix = pd.read_csv(f'{BASE}/data/raw/df_matrix.csv')
df_customer = pd.read_csv(f'{BASE}/data/raw/df_customer.csv')
df_loc = pd.read_csv(f'{BASE}/data/raw/df_loc.csv')

dur = {}
dist_m = {}
for _, r in df_matrix.iterrows():
    dur[(r['From'], r['To'])] = r['Duration']
    dur[(r['To'], r['From'])] = r['Duration']
    dist_m[(r['From'], r['To'])] = r['Distance']
    dist_m[(r['To'], r['From'])] = r['Distance']

def loss_per_ton(minutes):
    if minutes <= 500:
        return 0.0
    return 0.2 * (minutes - 500) ** 2 / 10000

# 坐标
loc_map = {}
for _, row in df_loc.iterrows():
    loc_map[row['Location']] = (row['Longitude'], row['Latitude'])

wh_loc_map = {}
for _, row in df_wh.iterrows():
    wh_loc_map[row['Name']] = row['Location']

def get_coords(name):
    if name in loc_map:
        return loc_map[name]
    if name in wh_loc_map:
        city = wh_loc_map[name]
        if city in loc_map:
            return loc_map[city]
    return None

# 仓库列表
cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].tolist()
rdc_names = df_wh[df_wh['Type'] == 'RDC']['Name'].tolist()
port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]
inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]

# 确定性模型的16个RDC
det_rdcs = ['bei-jing-DC', 'chang-sha-DC', 'chong-qing-DC', 'da-lian-DC',
            'dong-guan-DC', 'guang-zhou-DC', 'ha-er-bin-DC', 'hang-zhou-DC',
            'nan-jing-DC', 'ning-bo-DC', 'qing-dao-DC', 'shang-hai-DC',
            'tian-jin-DC', 'wu-han-DC', 'xi-an-DC', 'zheng-zhou-DC']

# 鲁棒模型的13个RDC
with open(f'{BASE}/results/question4/problem4_robust/robust_results.json', 'r', encoding='utf-8') as f:
    rob = json.load(f)
rob_rdcs = rob[0]['open_warehouses']

only_det = [w for w in det_rdcs if w not in rob_rdcs]
only_rob = [w for w in rob_rdcs if w not in det_rdcs]
common = [w for w in det_rdcs if w in rob_rdcs]

print(f"共同仓库 ({len(common)}): {common}")
print(f"仅确定性 ({len(only_det)}): {only_det}")
print(f"仅鲁棒 ({len(only_rob)}): {only_rob}")

# ========== 图1: 仓库选址对比地图 ==========
fig, axes = plt.subplots(1, 2, figsize=(20, 9))

for ax_idx, (title, selected_rdcs, color) in enumerate([
    (f'确定性模型: {len(det_rdcs)}个RDC', det_rdcs, '#e74c3c'),
    (f'鲁棒模型: {len(rob_rdcs)}个RDC', rob_rdcs, '#2ecc71')
]):
    ax = axes[ax_idx]
    
    # 画门店
    for _, row in df_customer.iterrows():
        name = row['Name']
        coords = get_coords(name)
        if coords:
            lng, lat = coords
            ax.plot(lng, lat, '.', color='gray', markersize=3, alpha=0.4)
    
    for cdc in cdc_names:
        coords = get_coords(cdc)
        if not coords:
            continue
        cdc_lng, cdc_lat = coords
        
        for rdc in selected_rdcs:
            rdc_coords = get_coords(rdc)
            if not rdc_coords:
                continue
            rdc_lng, rdc_lat = rdc_coords
            d = dur.get((cdc, rdc), 9999)
            loss = loss_per_ton(d)
            lw = min(loss * 2, 8)
            alpha = min(loss / 10, 0.8)
            
            if loss > 5:
                line_color = '#e74c3c'
            elif loss > 1:
                line_color = '#f39c12'
            elif loss > 0:
                line_color = '#27ae60'
            else:
                line_color = '#3498db'
            
            ax.plot([cdc_lng, rdc_lng], [cdc_lat, rdc_lat], '-',
                   color=line_color, linewidth=max(lw, 0.5), alpha=max(alpha, 0.2))
    
    # 画CDC
    for cdc in cdc_names:
        coords = get_coords(cdc)
        if coords:
            lng, lat = coords
            ax.plot(lng, lat, 's', color='gold', markersize=14, 
                   markeredgecolor='black', markeredgewidth=2, zorder=10)
            label = '港口CDC' if 'gang-kou' in cdc else '内陆CDC'
            ax.annotate(label, (lng, lat), fontsize=8, fontweight='bold',
                       xytext=(5, 5), textcoords='offset points')
    
    for rdc in selected_rdcs:
        coords = get_coords(rdc)
        if not coords:
            continue
        lng, lat = coords
        
        if rdc in only_det:
            marker = '^'
            ec = 'red'
            fc = '#ff6b6b'
            ms = 10
        elif rdc in only_rob:
            marker = 'D'
            ec = 'green'
            fc = '#51cf66'
            ms = 10
        else:
            marker = 'o'
            ec = 'black'
            fc = color
            ms = 8
        
        ax.plot(lng, lat, marker, color=fc, markersize=ms,
               markeredgecolor=ec, markeredgewidth=1.5, zorder=9)
        
        city = rdc.replace('-DC', '').replace('-', ' ')
        ax.annotate(city, (lng, lat), fontsize=6, 
                   xytext=(3, 3), textcoords='offset points')
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('经度')
    ax.set_ylabel('纬度')
    ax.set_xlim(73, 136)
    ax.set_ylim(18, 54)
    ax.grid(True, alpha=0.3)

# 图例
legend_elements = [
    Line2D([0], [0], marker='s', color='w', markerfacecolor='gold', 
           markeredgecolor='black', markersize=12, label='CDC'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='gray', 
           markersize=8, label='共有RDC'),
    Line2D([0], [0], marker='^', color='w', markerfacecolor='#ff6b6b',
           markeredgecolor='red', markersize=10, label='仅确定性模型'),
    Line2D([0], [0], marker='D', color='w', markerfacecolor='#51cf66',
           markeredgecolor='green', markersize=10, label='仅鲁棒模型'),
    Line2D([0], [0], color='#3498db', linewidth=2, label='CDC→RDC (无损)'),
    Line2D([0], [0], color='#27ae60', linewidth=2, label='CDC→RDC (低损耗)'),
    Line2D([0], [0], color='#f39c12', linewidth=3, label='CDC→RDC (中损耗)'),
    Line2D([0], [0], color='#e74c3c', linewidth=5, label='CDC→RDC (高损耗)'),
    Line2D([0], [0], marker='.', color='gray', markersize=5, 
           linestyle='None', label='门店'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=5, fontsize=9)
plt.tight_layout(rect=[0, 0.08, 1, 1])
plt.savefig(f'{BASE}/results/question4/problem4_robust/warehouse_comparison_map.png', 
            dpi=150, bbox_inches='tight')
plt.close()
print("图1已保存")

# ========== 图2: 第一性原理分析 ==========
fig, axes = plt.subplots(1, 3, figsize=(20, 7))

# 2a: CDC→RDC 运输时间对比
ax = axes[0]
det_cdc_durs = []
rob_cdc_durs = []

for rdc in det_rdcs:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d:
            det_cdc_durs.append(d)

for rdc in rob_rdcs:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d:
            rob_cdc_durs.append(d)

bins = np.arange(0, 2500, 100)
ax.hist(det_cdc_durs, bins=bins, alpha=0.6, color='#e74c3c', label=f'确定性 ({len(det_cdc_durs)}条)', density=False)
ax.hist(rob_cdc_durs, bins=bins, alpha=0.6, color='#2ecc71', label=f'鲁棒 ({len(rob_cdc_durs)}条)', density=False)
ax.axvline(x=500, color='blue', linestyle='--', linewidth=2, label='损耗阈值(500min)')
ax.set_xlabel('CDC→RDC 运输时间 (分钟)')
ax.set_ylabel('路线数量')
ax.set_title('CDC→RDC 运输时间分布', fontweight='bold')
ax.legend()

# 2b: 损耗成本 vs 运输时间 (二次函数)
ax = axes[1]
t_range = np.arange(0, 2000, 1)
loss_range = [loss_per_ton(t) for t in t_range]
ax.plot(t_range, loss_range, 'b-', linewidth=2, label='0.2×(t-500)²/10000')
ax.fill_between(t_range, loss_range, alpha=0.15, color='blue')

# 标注关键点
for rdc in only_det:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d and d > 500:
            l = loss_per_ton(d)
            city = rdc.replace('-DC','').replace('-',' ')
            ax.plot(d, l, 'r^', markersize=12, zorder=10)
            ax.annotate(f'{city}\n{d}min={l:.1f}万/吨', (d, l), fontsize=7,
                       xytext=(10, 5), textcoords='offset points', color='red')

for rdc in common:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d and d > 500:
            l = loss_per_ton(d)
            ax.plot(d, l, 'ko', markersize=6, alpha=0.5, zorder=9)

ax.axvline(x=500, color='blue', linestyle='--', alpha=0.5)
ax.set_xlabel('运输时间 (分钟)')
ax.set_ylabel('损耗 (万元/吨)')
ax.set_title('二次损耗函数：时间越长，损耗爆炸式增长', fontweight='bold')
ax.legend()
ax.set_xlim(0, 2200)
ax.set_ylim(0, 50)

# 2c: 两层运输的损耗分解
ax = axes[2]

det_cdc_loss_total = 0
det_rdc_loss_total = 0
rob_cdc_loss_total = 0
rob_rdc_loss_total = 0

# 确定性
for rdc in det_rdcs:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d:
            det_cdc_loss_total += loss_per_ton(d)
    for c in df_customer['Name']:
        d = dur.get((rdc, c))
        if d:
            det_rdc_loss_total += loss_per_ton(d)

# 鲁棒
for rdc in rob_rdcs:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d:
            rob_cdc_loss_total += loss_per_ton(d)
    for c in df_customer['Name']:
        d = dur.get((rdc, c))
        if d:
            rob_rdc_loss_total += loss_per_ton(d)

categories = ['确定性模型\n(16 RDC)', '鲁棒模型\n(13 RDC)']
cdc_losses = [det_cdc_loss_total, rob_cdc_loss_total]
rdc_losses = [det_rdc_loss_total, rob_rdc_loss_total]

x = np.arange(len(categories))
w = 0.5
bars1 = ax.bar(x, cdc_losses, w, label='CDC→RDC 损耗率之和', color='#e74c3c', alpha=0.8)
bars2 = ax.bar(x, rdc_losses, w, bottom=cdc_losses, label='RDC→门店 损耗率之和', color='#3498db', alpha=0.8)

for i, (c, r) in enumerate(zip(cdc_losses, rdc_losses)):
    ax.text(i, c/2, f'CDC→RDC\n{c:.0f}', ha='center', va='center', fontsize=10, fontweight='bold', color='white')
    ax.text(i, c + r/2, f'RDC→门店\n{r:.0f}', ha='center', va='center', fontsize=10, fontweight='bold', color='white')
    ax.text(i, c + r + 5, f'总计: {c+r:.0f}', ha='center', fontsize=10, fontweight='bold')

ax.set_ylabel('损耗率之和 (万元/吨)')
ax.set_title('两层运输损耗分解\n(每吨货物的平均损耗成本)', fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(categories)
ax.legend()

plt.tight_layout()
plt.savefig(f'{BASE}/results/question4/problem4_robust/first_principles_analysis.png',
            dpi=150, bbox_inches='tight')
plt.close()
print("图2已保存")

# ========== 打印关键数据 ==========
print("\n" + "=" * 70)
print("第一性原理分析：为什么少开RDC反而更好")
print("=" * 70)

print("\n1. 被砍掉的3个RDC的CDC→RDC运输时间:")
for rdc in only_det:
    for cdc in cdc_names:
        d = dur.get((cdc, rdc))
        if d:
            l = loss_per_ton(d)
            print(f"  {cdc} → {rdc}: {d}分钟, 损耗={l:.2f}万/吨")

print("\n2. 二次损耗函数的关键性质:")
for t in [500, 600, 700, 800, 1000, 1200, 1500, 2000]:
    l = loss_per_ton(t)
    print(f"  t={t}min → 损耗={l:.2f}万/吨" + (" ← 阈值" if t==500 else ""))

print("\n3. 核心逻辑:")
print("  多开远RDC → 门店近了(RDC→门店省) → 但CDC→RDC远了(二次方爆炸)")
print("  少开远RDC → 门店远了(RDC→门店多付) → 但CDC→RDC近了(大幅节省)")
print("  因为 0.2×(t-500)² 是二次函数，CDC→RDC的节省远大于RDC→门店的额外成本")
