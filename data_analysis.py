import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 读取数据
print("读取数据...")
df_wh = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_wh.csv')
df_customer = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_customer.csv')
df_order = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_order.csv')
df_loc = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_loc.csv')
df_matrix = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_matrix.csv')
df_proc = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_proc.csv')
df_past_order = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_past_order.csv')

print("\n=== 数据基本信息 ===")

# 1. 仓库信息
print("\n1. 仓库信息:")
print(f"   仓库总数: {len(df_wh)}")
print(f"   仓库类型: {df_wh['Type'].value_counts().to_dict()}")
print("   前5个仓库:")
print(df_wh.head())

# 2. 客户信息
print("\n2. 客户信息:")
print(f"   客户总数: {len(df_customer)}")
print("   前5个客户:")
print(df_customer.head())

# 3. 订单信息
print("\n3. 订单信息:")
print(f"   订单总数: {len(df_order)}")
print(f"   SKU类型: {df_order['SKU'].unique()}")
print("   订单数量统计:")
print(df_order.groupby('SKU')['qty'].describe())
print("   前5个订单:")
print(df_order.head())

# 4. 配送矩阵
print("\n4. 配送矩阵:")
print(f"   配送路线总数: {len(df_matrix)}")
print(f"   平均距离: {df_matrix['Distance'].mean():.2f} 公里")
print(f"   平均时长: {df_matrix['Duration'].mean():.2f} 分钟")
print("   前5条路线:")
print(df_matrix.head())

# 5. 处理信息
print("\n5. 处理信息:")
print(f"   处理中心总数: {len(df_proc)}")
print(f"   总处理容量: {df_proc['Capacity'].sum():.2f}")
print(f"   平均处理费: {df_proc['Processing_fee'].mean():.6f}")
print("   前5个处理中心:")
print(df_proc.head())

# 6. 历史订单
print("\n6. 历史订单:")
print(f"   历史订单记录数: {len(df_past_order)}")
print(f"   日期范围: {df_past_order.columns[2:].min()} 到 {df_past_order.columns[2:].max()}")
print(f"   天数: {len(df_past_order.columns[2:])}")
print("   前5条历史订单:")
print(df_past_order.head())

# 7. 地理位置信息
print("\n7. 地理位置信息:")
print(f"   位置总数: {len(df_loc)}")
print("   前5个位置:")
print(df_loc.head())

# 数据可视化
print("\n=== 数据可视化 ===")

# 1. 仓库类型分布
plt.figure(figsize=(8, 6))
df_wh['Type'].value_counts().plot(kind='pie', autopct='%1.1f%%', startangle=90)
plt.title('仓库类型分布')
plt.ylabel('')
plt.savefig('./仓库类型分布.png', dpi=300, bbox_inches='tight')

# 2. SKU订单数量分布
plt.figure(figsize=(8, 6))
df_order.groupby('SKU')['qty'].sum().plot(kind='bar')
plt.title('SKU订单总量分布')
plt.xlabel('SKU')
plt.ylabel('总数量')
plt.xticks(rotation=0)
plt.savefig('./SKU订单总量分布.png', dpi=300, bbox_inches='tight')

# 3. 处理中心容量分布
plt.figure(figsize=(12, 6))
sns.barplot(x='Name', y='Capacity', data=df_proc, palette='viridis')
plt.title('处理中心容量分布')
plt.xlabel('处理中心')
plt.ylabel('容量')
plt.xticks(rotation=90)
plt.tight_layout()
plt.savefig('./处理中心容量分布.png', dpi=300, bbox_inches='tight')

# 4. 历史订单趋势
plt.figure(figsize=(12, 6))
dates = df_past_order.columns[2:]
sku_dm = df_past_order[df_past_order['SKU'] == 'dm'].iloc[:, 2:].sum().values
sku_im = df_past_order[df_past_order['SKU'] == 'im'].iloc[:, 2:].sum().values

plt.plot(dates, sku_dm, label='dm', marker='o')
plt.plot(dates, sku_im, label='im', marker='o')
plt.title('历史订单数量趋势')
plt.xlabel('日期')
plt.ylabel('总数量')
plt.legend()
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('./历史订单趋势.png', dpi=300, bbox_inches='tight')

print("\n数据可视化完成，图表已保存到当前目录。")

# 计算总需求
total_demand = df_order['qty'].sum()
print(f"\n=== 总需求分析 ===")
print(f"   当前总订单需求: {total_demand:.2f}")
print(f"   处理中心总容量: {df_proc['Capacity'].sum():.2f}")
print(f"   容量充足率: {(df_proc['Capacity'].sum() / total_demand * 100):.2f}%")

# 分析需求与仓库覆盖
print("\n=== 需求与仓库覆盖分析 ===")
print("   正在分析需求分布与仓库覆盖情况...")

# 创建一个基本的分析报告
with open('./数据分析报告.txt', 'w', encoding='utf-8') as f:
    f.write("生鲜商品仓网配送优化项目数据分析报告\n")
    f.write("=" * 50 + "\n\n")
    
    f.write("一、数据概览\n")
    f.write(f"1. 仓库总数: {len(df_wh)}\n")
    f.write(f"2. 客户总数: {len(df_customer)}\n")
    f.write(f"3. 订单总数: {len(df_order)}\n")
    f.write(f"4. SKU类型: {', '.join(df_order['SKU'].unique())}\n")
    f.write(f"5. 总需求: {total_demand:.2f}\n")
    f.write(f"6. 总处理容量: {df_proc['Capacity'].sum():.2f}\n")
    
    f.write("\n二、仓库分析\n")
    f.write(f"1. 仓库类型分布: {df_wh['Type'].value_counts().to_dict()}\n")
    
    f.write("\n三、订单分析\n")
    f.write(f"1. dm类型总需求: {df_order[df_order['SKU'] == 'dm']['qty'].sum():.2f}\n")
    f.write(f"2. im类型总需求: {df_order[df_order['SKU'] == 'im']['qty'].sum():.2f}\n")
    
    f.write("\n四、处理中心分析\n")
    f.write(f"1. 最大容量处理中心: {df_proc.loc[df_proc['Capacity'].idxmax(), 'Name']} ({df_proc['Capacity'].max():.2f})\n")
    f.write(f"2. 最小容量处理中心: {df_proc.loc[df_proc['Capacity'].idxmin(), 'Name']} ({df_proc['Capacity'].min():.2f})\n")
    f.write(f"3. 平均处理费: {df_proc['Processing_fee'].mean():.6f}\n")
    
    f.write("\n五、配送分析\n")
    f.write(f"1. 最长距离: {df_matrix['Distance'].max():.2f} 公里\n")
    f.write(f"2. 最短距离: {df_matrix['Distance'].min():.2f} 公里\n")
    f.write(f"3. 平均距离: {df_matrix['Distance'].mean():.2f} 公里\n")

print("\n数据分析报告已生成: ./数据分析报告.txt")
print("\n数据初步分析完成!")