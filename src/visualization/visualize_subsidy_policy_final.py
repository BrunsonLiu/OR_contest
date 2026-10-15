# -*- coding: utf-8 -*-
"""
补贴政策影响可视化脚本 - 差值图版本

使用差值图（只显示变化量）来更清晰地展示补贴政策的影响
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import os
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

plt.style.use('seaborn-v0_8-white')
plt.rcParams['axes.facecolor'] = '#ffffff'
plt.rcParams['figure.facecolor'] = '#ffffff'
plt.rcParams['axes.edgecolor'] = '#2c3e50'
plt.rcParams['axes.linewidth'] = 1.5
plt.rcParams['grid.color'] = '#e8e8e8'
plt.rcParams['grid.linestyle'] = '-'
plt.rcParams['grid.linewidth'] = 0.8
plt.rcParams['axes.labelcolor'] = '#2c3e50'
plt.rcParams['xtick.color'] = '#555555'
plt.rcParams['ytick.color'] = '#555555'
plt.rcParams['legend.facecolor'] = '#fafafa'
plt.rcParams['legend.edgecolor'] = '#e0e0e0'
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']

print("="*80)
print("补贴政策影响可视化（差值图版本）")
print("="*80)

output_dir = str(_REPO_ROOT / 'results/question2')

print("\n【数据加载】")
try:
    df_subsidy = pd.read_csv(os.path.join(output_dir, '开仓补贴政策对比_cplex.csv'), encoding='utf-8-sig')
    print("  ✓ 开仓补贴政策对比_cplex.csv")
except Exception as e:
    print(f"  ✗ 加载失败: {e}")
    sys.exit(1)

print(f"\n【数据概览】")
print(f"  数据行数: {len(df_subsidy)}")
print(f"  方案类型: {df_subsidy['方案类型'].unique()}")

print("\n【数据预处理】")

no_subsidy = df_subsidy[df_subsidy['方案类型'] == '无补贴'].iloc[0]
with_subsidy = df_subsidy[df_subsidy['方案类型'] == '有补贴'].iloc[0]

print(f"\n  无补贴方案:")
print(f"    开仓数量: {no_subsidy['开仓数量']:.0f} 个")
print(f"    企业总成本: {no_subsidy['企业总物流成本（单位：万元）']:.2f} 万元")
print(f"    社会总成本: {no_subsidy['社会总成本（单位：万元）']:.2f} 万元")

print(f"\n  有补贴方案:")
print(f"    开仓数量: {with_subsidy['开仓数量']:.0f} 个")
print(f"    企业总成本: {with_subsidy['企业总物流成本（单位：万元）']:.2f} 万元")
print(f"    社会总成本: {with_subsidy['社会总成本（单位：万元）']:.2f} 万元")
print(f"    补贴金额: {with_subsidy['补贴金额（单位：万元）']:.2f} 万元")

cost_reduction = no_subsidy['企业总物流成本（单位：万元）'] - with_subsidy['企业总物流成本（单位：万元）']
subsidy_efficiency = cost_reduction / with_subsidy['补贴金额（单位：万元）'] if with_subsidy['补贴金额（单位：万元）'] > 0 else 0
wh_change = with_subsidy['开仓数量'] - no_subsidy['开仓数量']
rate_change = with_subsidy['时效满足率'] - no_subsidy['时效满足率']
social_change = with_subsidy['社会总成本（单位：万元）'] - no_subsidy['社会总成本（单位：万元）']

print("\n【可视化】")

try:
    fig, axes = plt.subplots(2, 1, figsize=(22, 14))
    fig.suptitle('补贴政策影响分析（差值图）', fontsize=24, fontweight='bold', fontproperties='SimHei', y=0.99, color='#2c3e50')
    
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c', '#34495e', '#e67e22']
    scheme_colors = {'无补贴': '#3498db', '有补贴': '#e74c3c'}
    
    # ==================== 图1：核心指标差值对比 ====================
    ax1 = axes[0, 0]
    
    metrics = ['开仓数量\n变化', '企业成本\n减少', '社会成本\n增加', '补贴金额\n支出']
    change_values = [wh_change, -cost_reduction, social_change, with_subsidy['补贴金额（单位：万元）']]
    
    x = np.arange(len(metrics))
    colors_bar = ['#2ecc71' if v >= 0 else '#e74c3c' for v in change_values]
    
    bars = ax1.bar(x, change_values, color=colors_bar, width=0.6, edgecolor='none', alpha=0.85)
    
    for i, (bar, val) in enumerate(zip(bars, change_values)):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (1 if val >= 0 else -1), 
                f'{val:+.2f}', ha='center', va='bottom' if val >= 0 else 'top',
                fontsize=16, fontweight='bold', color='#2c3e50')
    
    ax1.axhline(y=0, color='#2c3e50', linewidth=1.5, linestyle='-', alpha=0.6)
    ax1.set_ylabel('变化量（单位：个/万元）', fontsize=18, fontproperties='SimHei', fontweight='bold', color='#2c3e50')
    ax1.set_title('核心指标差值对比', fontsize=22, fontweight='bold', fontproperties='SimHei', color='#2c3e50')
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics, fontsize=14, fontproperties='SimHei')
    ax1.grid(True, axis='y', alpha=0.4, linewidth=1.0)
    ax1.tick_params(axis='x', pad=10)
    
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.savefig('补贴政策影响分析_差值图.png', dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print("\n  ✓ 已保存: 补贴政策影响分析_差值图.png")
    plt.close()
    
    print("\n【详细成本构成对比】")
    
    fig2, ax5 = plt.subplots(figsize=(20, 12))
    fig2.suptitle('补贴政策对成本构成的影响（差值图）', fontsize=22, fontweight='bold', fontproperties='SimHei', y=0.99, color='#2c3e50')
    
    x = np.arange(len(component_labels))
    width = 0.5
    
    bars = ax5.bar(x, cost_changes, color=colors_bar, width=width, edgecolor='none', alpha=0.85)
    
    for i, (bar, val) in enumerate(zip(bars, cost_changes)):
        if no_subsidy_costs[i] > 0:
            pct = (val / no_subsidy_costs[i]) * 100
            label = f'{val:+.1f} ({pct:+.1f}%)'
        else:
            label = f'{val:+.1f}'
        
        ax5.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (3 if val >= 0 else -3), 
                label, ha='center', va='bottom' if val >= 0 else 'top',
                fontsize=13, fontweight='bold', color='#2c3e50')
    
    ax5.axhline(y=0, color='#2c3e50', linewidth=1.5, linestyle='-', alpha=0.6)
    ax5.set_ylabel('变化量（万元）', fontsize=18, fontproperties='SimHei', fontweight='bold', color='#2c3e50')
    ax5.set_xlabel('成本构成', fontsize=18, fontproperties='SimHei', fontweight='bold', color='#2c3e50')
    ax5.set_title('成本构成差值对比', fontsize=22, fontweight='bold', fontproperties='SimHei', color='#2c3e50')
    ax5.set_xticks(x)
    ax5.set_xticklabels(component_labels, fontsize=13, fontproperties='SimHei', rotation=5, ha='right')
    ax5.grid(True, axis='y', alpha=0.4, linewidth=1.0)
    
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig('补贴政策_成本构成差值图.png', dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print("  ✓ 已保存: 补贴政策_成本构成差值图.png")
    plt.close()
    
    print("\n" + "="*80)
    print("【详细统计信息】")
    print("="*80)
    
    print("\n  方案对比表:")
    print("\n  指标 | 无补贴方案 | 有补贴方案 | 变化量 | 变化率")
    print("  " + "-"*90)
    
    metrics_comparison = [
        ('开仓数量', '开仓数量', '开仓数量', '{:.0f}', '{:+.0f}', '{:+.1f}%'),
        ('企业总物流成本', '企业总物流成本（单位：万元）', '企业总物流成本（单位：万元）', '{:.2f}', '{:.2f}', '{:+.2f}%'),
        ('社会总成本', '社会总成本（单位：万元）', '社会总成本（单位：万元）', '{:.2f}', '{:.2f}', '{:+.2f}%'),
        ('补贴金额', '补贴金额（单位：万元）', '补贴金额（单位：万元）', '{:.2f}', '{:+.2f}', '{:+.1f}%'),
        ('时效满足率', '时效满足率', '时效满足率', '{:.4f}', '{:.4f}', '{:+.4f}'),
    ]
    
    for metric_name, no_key, with_key, no_fmt, diff_fmt, rate_fmt in metrics_comparison:
        no_val = no_subsidy[no_key]
        with_val = with_subsidy[with_key]
        diff_val = with_val - no_val
        rate_val = (diff_val / no_val * 100) if no_val != 0 else 0
        
        if metric_name == '开仓数量':
            print(f"  {metric_name:12} | {no_val:.0f} | {with_val:.0f} | {diff_val:+.0f} | {rate_val:+.1f}%")
        else:
            print(f"  {metric_name:12} | {no_val:.2f} | {with_val:.2f} | {diff_val:+.2f} | {rate_val:+.2f}%")
    
    print("\n  成本构成对比（万元）:")
    print("\n  成本项 | 无补贴 | 有补贴 | 变化量 | 变化率")
    print("  " + "-"*90)
    
    for i, comp in enumerate(cost_components):
        no_val = no_subsidy_costs[i]
        with_val = with_subsidy_costs[i]
        change_val = cost_changes[i]
        rate_val = (change_val / no_val * 100) if no_val > 0 else 0
        
        print(f"  {component_labels[i]:12} | {no_val:8.2f} | {with_val:8.2f} | {change_val:+8.2f} | {rate_val:+7.2f}%")
    
    print("\n" + "="*80)
    print("【关键发现】")
    print("="*80)
    
    print("\n  1. 补贴政策效果：")
    print(f"     - 补贴金额: {with_subsidy['补贴金额（单位：万元）']:.2f} 万元")
    print(f"     - 企业成本减少: {cost_reduction:.2f} 万元")
    print(f"     - 补贴效率: {subsidy_efficiency:.2f} 倍（每万元补贴减少企业成本{subsidy_efficiency:.2f}万元）")
    
    print("\n  2. 开仓数量变化：")
    print(f"     - 无补贴方案: {no_subsidy['开仓数量']:.0f} 个")
    print(f"     - 有补贴方案: {with_subsidy['开仓数量']:.0f} 个")
    print(f"     - 变化: {wh_change:+.0f} 个")
    
    print("\n  3. 成本构成变化：")
    for i, label in enumerate(component_labels):
        if cost_changes[i] < 0:
            print(f"     - {label}: 减少 {abs(cost_changes[i]):.2f} 万元 ({cost_changes[i]/no_subsidy_costs[i]*100:+.1f}%)")
        else:
            print(f"     - {label}: 增加 {cost_changes[i]:.2f} 万元 ({cost_changes[i]/no_subsidy_costs[i]*100:+.1f}%)")
    
    print("\n  4. 社会总成本：")
    print(f"     - 无补贴方案: {no_subsidy['社会总成本（单位：万元）']:.2f} 万元")
    print(f"     - 有补贴方案: {with_subsidy['社会总成本（单位：万元）']:.2f} 万元")
    print(f"     - 变化: {social_change:+.2f} 万元")
    
    print("\n  5. 时效满足率：")
    print(f"     - 无补贴方案: {no_subsidy['时效满足率']:.4f} ({no_subsidy['时效满足率']*100:.2f}%)")
    print(f"     - 有补贴方案: {with_subsidy['时效满足率']:.4f} ({with_subsidy['时效满足率']*100:.2f}%)")
    print(f"     - 变化: {rate_change:+.4f} ({rate_change*100:+.2f}%)")
    
    print("\n  6. 政策启示：")
    print("     - 补贴政策有效激励企业扩大仓网规模")
    print("     - 企业成本显著降低，补贴效率合理")
    print("     - 社会总成本略有变化，但企业受益明显")
    print("     - 时效满足率基本稳定，服务质量保持良好")
    
    print("\n================================================================================")
    print("可视化完成！")
    print("生成的PNG图片：")
    print("  - 补贴政策影响分析_差值图.png")
    print("  - 补贴政策_成本构成差值图.png")
    print("================================================================================")

except Exception as e:
    print(f"\n  ✗ 可视化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
