# -*- coding: utf-8 -*-
"""
问题1结果可视化脚本

使用 pyecharts 绘制中国地图，展示：
1. 仓库分布
2. 仓库处置订单量
3. 运输网络
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import os
from pyecharts import options as opts
from pyecharts.charts import Geo, Page, Bar, Line
from pyecharts.globals import ChartType, SymbolType, CurrentConfig

# 设置本地资源（避免网络问题）
CurrentConfig.ONLINE_HOST = "D:/Python3.12/Lib/site-packages/pyecharts/assets/"

print("="*80)
print("问题1结果可视化")
print("="*80)

# ==================== 数据加载 ====================
output_dir = str(_REPO_ROOT / 'results/question1')

print("\n【数据加载】")
try:
    df_business = pd.read_csv(os.path.join(output_dir, '仓网业务表现文件.csv'))
    print("  ✓ 仓网业务表现文件")
    
    df_supply = pd.read_csv(os.path.join(output_dir, '仓网供应关系文件.csv'))
    print("  ✓ 仓网供应关系文件")
    
    df_wh = pd.read_csv(os.path.join(output_dir, '仓库处置订单量文件.csv'))
    print("  ✓ 仓库处置订单量文件")
except Exception as e:
    print(f"  ✗ 加载失败: {e}")
    sys.exit(1)

# ==================== 仓库地理坐标映射 ====================
# 仓库名称到经纬度的映射（基于中国主要城市）
warehouse_coords = {
    # CDC（2个）
    'gang-kou-CDC': [113.8, 22.9],  # 广州
    'nei-lu-CDC': [116.4, 39.9],    # 北京
    
    # RDC（16个）
    'dong-guan-DC': [113.7, 23.1],  # 东莞
    'nan-jing-DC': [118.8, 32.0],   # 南京
    'wu-han-DC': [114.3, 30.6],     # 武汉
    'ha-er-bin-DC': [126.6, 45.8],  # 哈尔滨
    'bei-jing-DC': [116.4, 39.9],   # 北京
    'ning-bo-DC': [121.6, 29.9],    # 宁波
    'chong-qing-DC': [106.5, 29.6], # 重庆
    'shanghai-DC': [121.5, 31.2],   # 上海
    'shenzhen-DC': [114.1, 22.5],   # 深圳
    'guangzhou-DC': [113.3, 23.1],  # 广州
    'tianjin-DC': [117.2, 39.1],    # 天津
    'chengdu-DC': [104.1, 30.7],    # 成都
    'hangzhou-DC': [120.2, 30.3],   # 杭州
    'xi-an-DC': [108.9, 34.3],      # 西安
    'suzhou-DC': [120.6, 31.3],     # 苏州
    'qing-dao-DC': [120.4, 36.1],   # 青岛
    'xiamen-DC': [118.1, 24.5],     # 厦门
}

# ==================== 数据预处理 ====================
print("\n【数据预处理】")

# 1. 仓库处置订单量
wh_qty = {}
for _, row in df_wh.iterrows():
    wh = row['Name']
    qty = row['Qty（单位：吨）']
    if wh in warehouse_coords:
        if wh not in wh_qty:
            wh_qty[wh] = 0
        wh_qty[wh] += qty

print(f"  ✓ 处理 {len(wh_qty)} 个仓库的订单量")

# 2. 供应关系（用于绘制运输网络）
supply_links = []
for _, row in df_supply.iterrows():
    from_wh = row['Name']
    to_wh = row['Customer']
    qty = row['Qty（单位：吨）']
    
    if from_wh in warehouse_coords and to_wh in warehouse_coords:
        supply_links.append({
            'from': from_wh,
            'to': to_wh,
            'qty': qty
        })

print(f"  ✓ 处理 {len(supply_links)} 条运输关系")

# ==================== 可视化1：仓库分布 + 处置订单量 ====================
print("\n【可视化1】仓库分布地图（带订单量）...")

geo = (
    Geo()
    .add_schema(maptype="china")
)

# 添加仓库坐标
for wh, coords in warehouse_coords.items():
    geo.add_coordinate(wh, coords[0], coords[1])

# 添加仓库标记（带数量）
for wh, coords in warehouse_coords.items():
    qty = wh_qty.get(wh, 0)
    if qty > 0:
        geo.add(
            wh,
            [[wh, qty]],
            type_=ChartType.EFFECT_SCATTER,
            symbol_size=qty / 100,  # 根据数量调整大小
            color="red",
        )

geo.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
geo.set_global_opts(
    title_opts=opts.TitleOpts(
        title="问题1：仓库分布与处置订单量",
        subtitle=f"共 {len(wh_qty)} 个仓库",
        title_textstyle_opts=opts.TextStyleOpts(font_size=20)
    ),
    visualmap_opts=opts.VisualMapOpts(
        is_show=True,
        type_="size",
        max_=max(wh_qty.values()) if wh_qty else 1000,
        min_=min(wh_qty.values()) if wh_qty else 0,
        range_size=[5, 30],
        orient="vertical",
        pos_left="right",
        pos_top="center",
    ),
)

geo.render("问题1_仓库分布.html")
print("  ✓ 已保存: 问题1_仓库分布.html")

# ==================== 可视化2：运输网络 ====================
print("\n【可视化2】运输网络地图...")

geo2 = (
    Geo()
    .add_schema(maptype="china")
)

# 添加仓库坐标
for wh, coords in warehouse_coords.items():
    geo2.add_coordinate(wh, coords[0], coords[1])

# 添加运输连接
for link in supply_links[:100]:  # 只显示前100条（太多会卡）
    from_wh = link['from']
    to_wh = link['to']
    qty = link['qty']
    
    if from_wh in warehouse_coords and to_wh in warehouse_coords:
        geo2.add(
            f"{from_wh}→{to_wh}",
            [[from_wh, to_wh]],
            type_=ChartType.LINES,
            effect_opts=opts.EffectOpts(
                symbol=SymbolType.ARROW,
                symbol_size=3,
                color="blue",
            ),
            linestyle_opts=opts.LineStyleOpts(
                curve=0.2,
                opacity=0.6,
                width=qty / 500,  # 根据运量调整线宽
            ),
        )

geo2.set_series_opts(label_opts=opts.LabelOpts(is_show=False))
geo2.set_global_opts(
    title_opts=opts.TitleOpts(
        title="问题1：运输网络",
        subtitle=f"共 {len(supply_links)} 条运输路线",
        title_textstyle_opts=opts.TextStyleOpts(font_size=20)
    ),
)

geo2.render("问题1_运输网络.html")
print("  ✓ 已保存: 问题1_运输网络.html")

# ==================== 可视化3：业务指标对比 ====================
print("\n【可视化3】业务指标对比...")

# 从业务表现文件提取数据
periods = list(range(1, len(df_business) + 1))
costs = df_business['总物流成本（单位：万元）'].tolist()
open_counts = df_business['开仓数量'].tolist()
time_rates = (df_business['时效满足率'] * 100).tolist()

bar = (
    Bar()
    .add_xaxis(periods)
    .add_yaxis("总物流成本（万元）", costs, itemstyle_opts=opts.ItemStyleOpts(color="blue"))
    .add_yaxis("开仓数量", open_counts, itemstyle_opts=opts.ItemStyleOpts(color="green"))
    .set_global_opts(
        title_opts=opts.TitleOpts(
            title="问题1：业务指标趋势",
            subtitle="多周期对比",
            title_textstyle_opts=opts.TextStyleOpts(font_size=20)
        ),
        xaxis_opts=opts.AxisOpts(name="周期"),
        yaxis_opts=opts.AxisOpts(name="成本（万元）/数量"),
    )
)

line = (
    Line()
    .add_xaxis(periods)
    .add_yaxis(
        "时效满足率（%）",
        time_rates,
        yaxis_index=1,
        label_opts=opts.LabelOpts(is_show=True),
        linestyle_opts=opts.LineStyleOpts(color="red", width=3),
    )
)

# 双轴图
bar.overlap(line)
bar.set_global_opts(
    yaxis_opts=opts.AxisOpts(
        name="成本（万元）/数量",
        axislabel_opts=opts.LabelOpts(color="blue"),
    ),
)

bar.render("问题1_业务指标.html")
print("  ✓ 已保存: 问题1_业务指标.html")

# ==================== 可视化4：成本构成 ====================
print("\n【可视化4】成本构成分析...")

# 提取成本构成
transport_cost = df_business['仓库之间的运输总成本（单位：万元）'].tolist()
to_customer_cost = df_business['仓库到门店的运输总成本（单位：万元）'].tolist()
open_cost = df_business['开仓总成本（单位：万元）'].tolist()
process_cost = df_business['出入仓处置总成本（单位：万元）'].tolist()
smart_cost = df_business['智能调度系统采购总成本（单位：万元）'].tolist()

cost_breakdown = {
    '仓库间运输': transport_cost,
    '到门店运输': to_customer_cost,
    '开仓成本': open_cost,
    '处置成本': process_cost,
    '智能系统': smart_cost,
}

# 创建饼图
from pyecharts.charts import Pie

total_cost = sum(costs)
pie = (
    Pie()
    .add(
        "成本构成",
        [
            ("仓库间运输", sum(transport_cost)),
            ("到门店运输", sum(to_customer_cost)),
            ("开仓成本", sum(open_cost)),
            ("处置成本", sum(process_cost)),
            ("智能系统", sum(smart_cost)),
        ],
        radius=["40%", "70%"],
        label_opts=opts.LabelOpts(is_show=True, formatter="{b}: {c}万元 ({d}%)"),
    )
    .set_global_opts(
        title_opts=opts.TitleOpts(
            title="问题1：成本构成",
            subtitle=f"总成本: {total_cost:.2f}万元",
            title_textstyle_opts=opts.TextStyleOpts(font_size=20)
        ),
        legend_opts=opts.LegendOpts(orient="vertical", pos_left="left"),
    )
)

pie.render("问题1_成本构成.html")
print("  ✓ 已保存: 问题1_成本构成.html")

# ==================== 生成综合页面 ====================
print("\n【生成综合页面】...")

page = Page(layout=Page.DraggablePageLayout)
page.add(
    geo,
    geo2,
    bar,
    pie,
)
page.render("问题1_综合可视化.html")
print("  ✓ 已保存: 问题1_综合可视化.html")

print("\n" + "="*80)
print("可视化完成！")
print("打开以下文件查看结果：")
print("  - 问题1_仓库分布.html")
print("  - 问题1_运输网络.html")
print("  - 问题1_业务指标.html")
print("  - 问题1_成本构成.html")
print("  - 问题1_综合可视化.html")
print("="*80)
