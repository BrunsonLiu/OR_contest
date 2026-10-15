"""
对应论文文档: 问题3.md （文件: 问题3.md）
公式/符号对照
    - 历史序列 y_{1:T}，预测 H 日 y_{T+1:T+H}
    - 特征映射: 时间特征、滞后特征、城市特征；预测模型以 X->y 映射训练
    - 评价指标: RMSE, MAPE（文中给出公式，可直接引用）

实现提示:
    - 代码中主要函数 `advanced_forecast` 对应文档中的基线方法描述，可在论文中把模型训练/验证细节引用为“参见问题3.md 节 2-4”。
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
import os
from sklearn.preprocessing import LabelEncoder

# 创建输出目录
output_dir = str(_REPO_ROOT / 'results/question3')
os.makedirs(output_dir, exist_ok=True)

# 读取历史订单数据
df_past_order = pd.read_csv(str(_REPO_ROOT / 'data/raw/df_past_order.csv'))

print("历史订单数据读取完成...")
print(f"数据形状: {df_past_order.shape}")
print(f"日期范围: {df_past_order.columns[2:].min()} 到 {df_past_order.columns[2:].max()}")
print(f"总天数: {len(df_past_order.columns[2:])}")

# 数据预处理
print("\n数据预处理...")

# 1. 将日期列转换为时间序列
date_columns = df_past_order.columns[2:].tolist()
dates = pd.to_datetime(date_columns, format='%Y/%m/%d')
n_historical_days = len(dates)
print(f"历史数据天数: {n_historical_days}")
print(f"日期范围: {dates[0].strftime('%Y-%m-%d')} 到 {dates[-1].strftime('%Y-%m-%d')}")

# 2. 创建预测日期范围（2016-6-24到2016-6-30）
pred_dates = pd.date_range(start='2016-06-24', end='2016-06-30', freq='D')
pred_date_strings = [d.strftime('%Y/%m/%d') for d in pred_dates]

# 3. 数据验证：确保每行的历史数据长度一致
print("\n验证数据一致性...")
invalid_rows = []
for idx, row in df_past_order.iterrows():
    history = row.iloc[2:].values.astype(float)
    if len(history) != n_historical_days:
        invalid_rows.append((idx, row['Name'], row['SKU'], len(history)))

if invalid_rows:
    print(f"发现 {len(invalid_rows)} 行数据长度不一致:")
    for idx, name, sku, length in invalid_rows[:5]:  # 只显示前5个
        print(f"  - 行{idx}: {name}-{sku}, 长度={length}")
    # 清理无效行
    df_past_order = df_past_order.drop([r[0] for r in invalid_rows])
    print(f"已清理 {len(invalid_rows)} 行无效数据")
else:
    print("所有数据行长度一致 ✓")

print(f"有效数据行数: {len(df_past_order)}")

# 4. 创建城市编码器（基于真正的城市名）
city_names = df_past_order['Name'].apply(lambda x: x.rsplit('-', 1)[0]).tolist()
city_encoder = LabelEncoder()
city_encoder.fit(city_names)
n_cities = len(city_encoder.classes_)
print(f"检测到 {n_cities} 个城市")

# 特征标准化函数
def normalize_features(X, train_means=None, train_stds=None, fit=True):
    """标准化特征"""
    if fit:
        train_means = X.mean()
        train_stds = X.std()
        train_stds[train_stds == 0] = 1  # 避免除零
    
    X_normalized = (X - train_means) / train_stds
    
    return X_normalized, train_means, train_stds

# 5. 创建特征工程函数（包含城市特征）
def create_features_for_ts(ts_dates, city_code=None, values=None):
    """
    为时间序列创建特征（包含城市特征）
    """
    df = pd.DataFrame({'date': ts_dates})
    
    # 时间特征
    df['day_of_week'] = df['date'].dt.dayofweek
    df['day_of_month'] = df['date'].dt.day
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
    
    # 循环特征
    df['sin_day_of_week'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['cos_day_of_week'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    
    # 月份特征
    df['month'] = df['date'].dt.month
    df['sin_month'] = np.sin(2 * np.pi * df['month'] / 12)
    df['cos_month'] = np.cos(2 * np.pi * df['month'] / 12)
    
    # 时间索引
    df['time_idx'] = np.arange(len(df))
    
    # 城市特征
    if city_code is not None:
        df['city_code'] = city_code
    
    if values is not None:
        df['demand'] = values
    
    return df

# 6. 实现SOTA预测模型（GradientBoosting + 城市特征）
def advanced_forecast(history, history_dates, pred_dates, sku_type, city_code):
    """
    使用SOTA方法预测未来需求（GradientBoosting + 城市特征）
    """
    # 创建历史特征
    history_df = create_features_for_ts(history_dates, city_code, history)
    pred_df = create_features_for_ts(pred_dates, city_code)
    
    # 特征列
    feature_cols = ['time_idx', 'day_of_week', 'is_weekend', 'sin_day_of_week', 
                    'cos_day_of_week', 'day_of_month', 'month', 'sin_month', 'cos_month', 'city_code']
    
    X_train = history_df[feature_cols]
    y_train = history_df['demand']
    X_pred = pred_df[feature_cols]
    
    # 标准化特征
    X_train_normalized, means, stds = normalize_features(X_train, fit=True)
    X_pred_normalized, _, _ = normalize_features(X_pred, means, stds, fit=False)
    
    # 根据SKU类型选择模型
    if sku_type == 'dm':
        model = GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42)
    else:
        model = GradientBoostingRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, random_state=42)
    
    # 训练模型
    model.fit(X_train_normalized, y_train)
    
    # 预测
    y_pred = model.predict(X_pred_normalized)
    
    # 确保预测值不为负
    y_pred = np.maximum(y_pred, 0)
    
    # 后处理：周末效应调整
    for i, day in enumerate(pred_df['day_of_week']):
        if day in [5, 6]:
            weekend_history = history_df[history_df['is_weekend'] == 1]['demand'].mean()
            weekday_history = history_df[history_df['is_weekend'] == 0]['demand'].mean()
            if weekday_history > 0:
                weekend_adjustment = weekend_history / weekday_history
                y_pred[i] *= weekend_adjustment
    
    # 平滑处理
    if len(y_pred) > 1:
        for i in range(1, len(y_pred)):
            max_change = y_pred[i-1] * 1.3
            min_change = y_pred[i-1] * 0.7
            y_pred[i] = np.clip(y_pred[i], min_change, max_change)
    
    return y_pred

# 7. 开始预测和评估
print("\n开始SOTA预测（GradientBoosting + 城市特征）...")

predictions = []

for idx, row in df_past_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    city_name = store.rsplit('-', 1)[0]
    city_code = city_encoder.transform([city_name])[0]
    
    history = row.iloc[2:].values.astype(float)
    
    try:
        y_pred = advanced_forecast(history, dates, pred_dates, sku, city_code)
    except Exception as e:
        print(f"预测 {store}-{sku} 时出错: {e}")
        y_pred = np.full(7, np.mean(history))
    
    pred_row = [store, sku] + y_pred.tolist()
    predictions.append(pred_row)
    
    if (idx + 1) % 50 == 0:
        print(f"已完成 {idx + 1}/{len(df_past_order)} 条预测")

# 创建预测结果DataFrame
columns = ['Customer', 'SKU'] + pred_date_strings
predictions_df = pd.DataFrame(predictions, columns=columns)

# 保存预测结果
output_path = os.path.join(output_dir, '订单需求量预测结果文件.csv')
predictions_df.to_csv(output_path, index=False)

print(f"\n✅ SOTA预测完成！（GradientBoosting + 城市特征）")
print(f"预测结果已保存到: {output_path}")
print(f"预测结果形状: {predictions_df.shape}")

# ========== 评估预测效果 ==========
print("\n" + "=" * 60)
print("模型评估（使用历史最后7天作为验证集）")
print("=" * 60)

# 计算评估指标
def evaluate_predictions(df_past_order, predictions_df, dates):
    """计算预测评估指标（匹配之前对比方法）"""
    rmse_list = []
    mape_list = []
    
    for idx, row in df_past_order.iterrows():
        sku = row['SKU']
        history = row.iloc[2:].values.astype(float)
        pred = predictions_df.iloc[idx].iloc[2:].values.astype(float)
        
        # 用历史最后7天对比预测的7天
        rmse = np.sqrt(mean_squared_error(history[-7:], pred))
        rmse_list.append(rmse)
        
        # 计算MAPE
        mask = history[-7:] != 0
        if mask.sum() > 0:
            mape = mean_absolute_percentage_error(history[-7:][mask], pred[mask]) * 100
            mape_list.append(mape)
        else:
            mape_list.append(0)
    
    return np.mean(rmse_list), np.mean(mape_list), rmse_list, mape_list

# 按SKU类型分组评估
def evaluate_by_sku_type(df_past_order, predictions_df, dates):
    """按SKU类型计算评估指标"""
    dm_rmse, dm_mape = [], []
    im_rmse, im_mape = [], []
    
    for idx, row in df_past_order.iterrows():
        sku = row['SKU']
        history = row.iloc[2:].values.astype(float)
        pred = predictions_df.iloc[idx].iloc[2:].values.astype(float)
        
        rmse = np.sqrt(mean_squared_error(history[-7:], pred))
        
        mask = history[-7:] != 0
        mape = mean_absolute_percentage_error(history[-7:][mask], pred[mask]) * 100 if mask.sum() > 0 else 0
        
        if sku == 'dm':
            dm_rmse.append(rmse)
            dm_mape.append(mape)
        else:
            im_rmse.append(rmse)
            im_mape.append(mape)
    
    return {
        'dm': {'rmse': np.mean(dm_rmse), 'mape': np.mean(dm_mape)},
        'im': {'rmse': np.mean(im_rmse), 'mape': np.mean(im_mape)}
    }

# 计算评估指标
total_rmse, total_mape, rmse_list, mape_list = evaluate_predictions(df_past_order, predictions_df, dates)
results_by_sku = evaluate_by_sku_type(df_past_order, predictions_df, dates)

print(f"\n📊 模型评估结果：")
print(f"  Average RMSE: {total_rmse:.4f}")
print(f"  Average MAPE: {total_mape:.2f}%")
print(f"\n  DM类 - RMSE: {results_by_sku['dm']['rmse']:.4f}, MAPE: {results_by_sku['dm']['mape']:.2f}%")
print(f"  IM类 - RMSE: {results_by_sku['im']['rmse']:.4f}, MAPE: {results_by_sku['im']['mape']:.2f}%")

# ========== 验证误差分析（用于第四问随机优化）==========
print("\n" + "=" * 80)
print("【验证误差分析 - 用于第四问随机优化】")
print("=" * 80)

# 计算每个样本的预测误差
all_errors = []
all_true_values = []

for idx, row in df_past_order.iterrows():
    history = row.iloc[2:].values.astype(float)
    pred = predictions_df.iloc[idx].iloc[2:].values.astype(float)
    
    # 用历史最后7天作为真实值，对比预测的7天
    true_values = history[-7:]
    predicted_values = pred
    
    # 计算每个预测点的误差
    errors = true_values - predicted_values
    all_errors.extend(errors)
    all_true_values.extend(true_values)

# 计算误差统计
all_errors = np.array(all_errors)
all_true_values = np.array(all_true_values)

error_std = all_errors.std()
error_mean = all_errors.mean()
error_mae = np.abs(all_errors).mean()
error_rmse = np.sqrt(np.mean(all_errors ** 2))

# 计算相对误差（百分比）
relative_errors = np.abs(all_errors / (all_true_values + 1e-6))
relative_error_std = relative_errors.std()
relative_error_mean = relative_errors.mean()

print(f"\n【绝对误差统计】")
print(f"  误差标准差: {error_std:.4f}")
print(f"  误差均值: {error_mean:.4f}")
print(f"  平均绝对误差(MAE): {error_mae:.4f}")
print(f"  均方根误差(RMSE): {error_rmse:.4f}")

print(f"\n【相对误差统计（百分比）】")
print(f"  相对误差标准差: {relative_error_std*100:.2f}%")
print(f"  平均相对误差: {relative_error_mean*100:.2f}%")

print(f"\n【建议的波动参数（用于第四问随机优化）】")
print(f"  建议需求波动: ±{relative_error_std*100:.1f}%")
print(f"  （基于第三问实际验证误差估计）")

# 保存误差分析结果到文件
error_analysis_path = os.path.join(output_dir, 'Forecast_Error_Analysis.txt')
with open(error_analysis_path, 'w', encoding='utf-8') as f:
    f.write("Forecast Error Analysis Report (for Problem 4 Robust Optimization)\n")
    f.write("=" * 70 + "\n\n")
    f.write("Method: Compare last 7 days historical data vs forecasted 7 days\n")
    f.write("Model: GradientBoostingRegressor + Feature Engineering\n\n")
    f.write("【Absolute Error Statistics】\n")
    f.write(f"  Error Std: {error_std:.4f}\n")
    f.write(f"  Error Mean: {error_mean:.4f}\n")
    f.write(f"  Mean Absolute Error (MAE): {error_mae:.4f}\n")
    f.write(f"  Root Mean Squared Error (RMSE): {error_rmse:.4f}\n\n")
    f.write("【Relative Error Statistics (Percentage)】\n")
    f.write(f"  Relative Error Std: {relative_error_std*100:.2f}%\n")
    f.write(f"  Mean Relative Error: {relative_error_mean*100:.2f}%\n\n")
    f.write("【Recommended Uncertainty Parameter (for Problem 4)】\n")
    f.write(f"  Recommended Demand Uncertainty: ±{relative_error_std*100:.1f}%\n")
    f.write(f"  (Based on actual validation error from Problem 3)\n\n")
    f.write("Note: Use this uncertainty parameter in Problem 4's scenario generation\n")
    f.write("     to ensure consistency between Problem 3 and Problem 4.\n")
    f.write("=" * 70 + "\n")

print(f"\n✅ 验证误差分析已保存到: {error_analysis_path}")

# Visualize example forecast results
print("\nVisualizing example forecast results...")

fig, axes = plt.subplots(2, 2, figsize=(12, 8))
fig.suptitle('SOTA Forecast Examples (GradientBoosting + City Features)', fontsize=16)

valid_count = 0
for i in range(len(predictions_df)):
    if valid_count >= 4:
        break
    
    store = predictions_df.iloc[i]['Customer']
    sku = predictions_df.iloc[i]['SKU']
    
    history = df_past_order.iloc[i].iloc[2:].values.astype(float)
    pred = predictions_df.iloc[i].iloc[2:].values.astype(float)
    
    n_hist = len(history)
    hist_dates = dates[:n_hist]
    
    if len(hist_dates) != n_hist:
        continue
    
    ax = axes[valid_count // 2, valid_count % 2]
    ax.plot(hist_dates, history, 'o-', label='Historical Demand')
    ax.plot(pred_dates, pred, 's-', label='Forecast Demand')
    
    # Mark weekends
    for j, date in enumerate(hist_dates):
        if date.dayofweek in [5, 6]:
            ax.axvline(x=date, color='gray', alpha=0.2, linestyle='--')
    for j, date in enumerate(pred_dates):
        if date.dayofweek in [5, 6]:
            ax.axvline(x=date, color='gray', alpha=0.4, linestyle='--')
    
    ax.set_title(f'{store} - {sku}')
    ax.legend()
    ax.set_xlabel('Date')
    ax.set_ylabel('Demand')
    ax.tick_params(axis='x', rotation=45)
    valid_count += 1

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'SOTA_Forecast_Examples.png'), dpi=150, bbox_inches='tight')
plt.close()

print(f"可视化结果已保存到: {os.path.join(output_dir, 'SOTA_Forecast_Examples.png')}")

# 生成性能报告
report_path = os.path.join(output_dir, 'Forecast_Performance_Report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write("Order Demand Forecast Performance Report\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Forecast Method: Gradient Boosting Regression + Feature Engineering\n")
    f.write(f"Features: Time Index, Day of Week, Weekend Indicator, Periodic Features, City\n")
    f.write(f"Historical Data Date Range: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}\n")
    f.write(f"Forecast Date Range: {pred_dates[0].strftime('%Y-%m-%d')} to {pred_dates[-1].strftime('%Y-%m-%d')}\n")
    f.write(f"Total Forecast Entries: {len(predictions)}\n")
    f.write(f"Validation Method: Last 7 days vs Forecast 7 days\n")
    f.write(f"Average RMSE: {total_rmse:.4f}\n")
    f.write(f"Average MAPE: {total_mape:.2f}%\n\n")
    f.write("Model Features:\n")
    f.write("1. Different parameters for SKU types (dm/im)\n")
    f.write("2. Feature normalization\n")
    f.write("3. Weekend effect adjustment\n")
    f.write("4. Smoothing to avoid excessive forecast volatility\n")
    f.write("5. Non-negative forecast values guarantee\n")
    f.write("6. Enhanced weekly periodicity handling\n")
    f.write("7. Sin/Cos transformed monthly features for periodicity\n")
    f.write("=" * 50 + "\n")

print(f"性能报告已保存到: {report_path}")