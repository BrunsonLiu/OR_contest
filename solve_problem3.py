import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler
import os

# 创建输出目录
output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
os.makedirs(output_dir, exist_ok=True)

# 读取历史订单数据
df_past_order = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_past_order.csv')

print("历史订单数据读取完成...")
print(f"数据形状: {df_past_order.shape}")
print(f"日期范围: {df_past_order.columns[2:].min()} 到 {df_past_order.columns[2:].max()}")
print(f"总天数: {len(df_past_order.columns[2:])}")

# 数据预处理
print("\n数据预处理...")

# 1. 将日期列转换为时间序列
dates = pd.to_datetime(df_past_order.columns[2:], format='%Y/%m/%d')

# 2. 创建预测日期范围（2016-6-24到2016-6-30）
pred_dates = pd.date_range(start='2016-06-24', end='2016-06-30', freq='D')
pred_date_strings = [d.strftime('%Y/%m/%d') for d in pred_dates]

# 3. 按门店和SKU分组进行预测
print("\n开始预测...")

# 创建预测结果数据框
predictions = []

# 对每个门店和SKU分别进行预测
for _, row in df_past_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    
    # 获取历史需求数据
    history = row.iloc[2:].values.astype(float)
    
    # 创建特征：时间索引
    X = np.arange(len(history)).reshape(-1, 1)
    y = history.reshape(-1, 1)
    
    # 使用线性回归模型预测
    model = LinearRegression()
    model.fit(X, y)
    
    # 预测未来7天
    X_pred = np.arange(len(history), len(history) + 7).reshape(-1, 1)
    y_pred = model.predict(X_pred)
    
    # 确保预测值不为负
    y_pred = np.maximum(y_pred, 0)
    
    # 将结果添加到预测列表
    pred_row = [store, sku] + y_pred.flatten().tolist()
    predictions.append(pred_row)

# 创建预测结果DataFrame
columns = ['Customer', 'SKU'] + pred_date_strings
predictions_df = pd.DataFrame(predictions, columns=columns)

# 保存预测结果
output_path = os.path.join(output_dir, '订单需求量预测结果文件.csv')
predictions_df.to_csv(output_path, index=False)

print(f"\n预测完成！")
print(f"预测结果已保存到: {output_path}")
print(f"预测结果形状: {predictions_df.shape}")

# 可视化示例预测结果
print("\n可视化示例预测结果...")

# 选择前4个门店-SKU组合进行可视化
fig, axes = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle('历史需求与预测结果示例', fontsize=16)

for i in range(4):
    if i < len(predictions):
        store = predictions_df.iloc[i]['Customer']
        sku = predictions_df.iloc[i]['SKU']
        
        # 获取历史数据
        history = df_past_order.iloc[i].iloc[2:].values.astype(float)
        
        # 获取预测数据
        pred = predictions_df.iloc[i].iloc[2:].values.astype(float)
        
        # 绘制图表
        ax = axes[i // 2, i % 2]
        ax.plot(dates, history, 'o-', label='历史需求')
        ax.plot(pred_dates, pred, 's-', label='预测需求')
        ax.set_title(f'{store} - {sku}')
        ax.set_xlabel('日期')
        ax.set_ylabel('需求量（吨）')
        ax.legend()
        ax.tick_params(axis='x', rotation=45)

plt.tight_layout()
plt.subplots_adjust(top=0.9)

# 保存可视化结果
plt.savefig(os.path.join(output_dir, '预测结果示例.png'), dpi=300, bbox_inches='tight')

# 计算预测性能（使用历史数据的最后7天作为验证）
print("\n计算预测性能...")

# 对于每个门店-SKU组合，使用前16天预测后7天
rmse_scores = []

for _, row in df_past_order.iterrows():
    # 获取历史数据
    history = row.iloc[2:].values.astype(float)
    
    # 划分训练集和验证集
    X_train = np.arange(16).reshape(-1, 1)
    y_train = history[:16].reshape(-1, 1)
    
    X_test = np.arange(16, 23).reshape(-1, 1)
    y_test = history[16:].reshape(-1, 1)
    
    # 训练模型
    model = LinearRegression()
    model.fit(X_train, y_train)
    
    # 预测验证集
    y_pred = model.predict(X_test)
    
    # 计算RMSE
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    rmse_scores.append(rmse)

# 计算平均RMSE
avg_rmse = np.mean(rmse_scores)
print(f"平均RMSE: {avg_rmse:.4f}")

# 保存性能报告
with open(os.path.join(output_dir, '预测性能报告.txt'), 'w', encoding='utf-8') as f:
    f.write("订单需求量预测性能报告\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"预测方法: 线性回归\n")
    f.write(f"历史数据日期范围: {dates.min().strftime('%Y-%m-%d')} 到 {dates.max().strftime('%Y-%m-%d')}\n")
    f.write(f"预测日期范围: {pred_dates.min().strftime('%Y-%m-%d')} 到 {pred_dates.max().strftime('%Y-%m-%d')}\n")
    f.write(f"总预测条数: {len(predictions_df)}\n")
    f.write(f"平均RMSE: {avg_rmse:.4f}\n")

print("\n预测性能报告已生成！")
print("所有任务完成！")