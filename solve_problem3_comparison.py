"""
实验一与实验二对比：城市特征对预测效果的影响

实验一：纯时间序列预测（现有方法）
实验二：加入城市特征（经纬度、人口、GDP等）的预测
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
import os
import warnings
warnings.filterwarnings('ignore')

# 创建输出目录
output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
os.makedirs(output_dir, exist_ok=True)

print("=" * 60)
print("实验一与实验二对比：城市特征对预测效果的影响")
print("=" * 60)

# 读取历史订单数据
df_past_order = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_past_order.csv')
print(f"历史订单数据读取完成... 形状: {df_past_order.shape}")

# 读取城市信息数据
df_loc = pd.read_csv('./2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data/df_loc.csv')
print(f"城市信息数据读取完成... 形状: {df_loc.shape}")
print(f"城市信息列: {df_loc.columns.tolist()}")

# 数据预处理
dates = pd.to_datetime(df_past_order.columns[2:], format='%Y/%m/%d')
pred_dates = pd.date_range(start='2016-06-24', end='2016-06-30', freq='D')
pred_date_strings = [d.strftime('%Y/%m/%d') for d in pred_dates]

# 创建城市特征映射
def get_city_features(city_name, df_loc):
    """
    获取城市的特征信息
    """
    # 尝试精确匹配
    city_data = df_loc[df_loc['Location'].str.lower() == city_name.lower()]
    
    if city_data.empty:
        # 尝试模糊匹配
        city_data = df_loc[df_loc['Location'].str.lower().str.contains(city_name.lower().split('-')[0])]
    
    if city_data.empty:
        # 返回默认值
        return {
            'Longitude': 116.4,  # 默认北京经度
            'Latitude': 39.9,    # 默认北京纬度
            'city_area': 10000,
            'builtup_area': 500,
            'resident_pop': 500,
            'gdp': 5000
        }
    
    row = city_data.iloc[0]
    return {
        'Longitude': row['Longitude'] if pd.notna(row['Longitude']) else 116.4,
        'Latitude': row['Latitude'] if pd.notna(row['Latitude']) else 39.9,
        'city_area': row['city_area'] if pd.notna(row['city_area']) else 10000,
        'builtup_area': row['builtup_area'] if pd.notna(row['builtup_area']) else 500,
        'resident_pop': row['resident_pop'] if pd.notna(row['resident_pop']) else 500,
        'gdp': row['gdp'] if pd.notna(row['gdp']) else 5000
    }

# 特征工程函数
def create_time_features(ts_dates):
    """创建时间序列特征"""
    df = pd.DataFrame({'date': ts_dates})
    df['day_of_week'] = df['date'].dt.dayofweek
    df['day_of_month'] = df['date'].dt.day
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['week_of_year'] = df['date'].dt.isocalendar().week.astype(int)
    df['sin_day_of_week'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['cos_day_of_week'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['time_idx'] = np.arange(len(df))
    
    # 月份特征
    df['month'] = df['date'].dt.month
    df['sin_month'] = np.sin(2 * np.pi * df['month'] / 12)
    df['cos_month'] = np.cos(2 * np.pi * df['month'] / 12)
    
    return df

def create_city_features(city_name, df_loc, ts_dates):
    """创建城市特征"""
    city_data = get_city_features(city_name, df_loc)
    n = len(ts_dates)
    
    return {
        'Longitude': np.full(n, city_data['Longitude']),
        'Latitude': np.full(n, city_data['Latitude']),
        'city_area': np.full(n, city_data['city_area']),
        'builtup_area': np.full(n, city_data['builtup_area']),
        'resident_pop': np.full(n, city_data['resident_pop']),
        'gdp': np.full(n, city_data['gdp']),
        # 派生特征：人口密度
        'pop_density': np.full(n, city_data['resident_pop'] / city_data['city_area'] * 1000 if city_data['city_area'] > 0 else 0),
        # 派生特征：经济密度
        'gdp_density': np.full(n, city_data['gdp'] / city_data['city_area'] if city_data['city_area'] > 0 else 0)
    }

def normalize_features(X, train_means=None, train_stds=None, fit=True):
    """标准化特征"""
    if fit:
        train_means = X.mean()
        train_stds = X.std()
        train_stds[train_stds == 0] = 1  # 避免除零
    
    X_normalized = (X - train_means) / train_stds
    
    return X_normalized, train_means, train_stds

# ========== 实验一：纯时间序列预测 ==========
def experiment_1_forecast(history, history_dates, pred_dates, sku_type):
    """
    实验一：纯时间序列预测（现有方法）
    只使用时间特征
    """
    history_df = create_time_features(history_dates)
    history_df['demand'] = history
    
    pred_df = create_time_features(pred_dates)
    
    # 时间特征列
    feature_cols = ['time_idx', 'day_of_week', 'is_weekend', 'sin_day_of_week', 
                   'cos_day_of_week', 'day_of_month', 'month', 'sin_month', 'cos_month']
    
    X_train = history_df[feature_cols]
    y_train = history_df['demand']
    X_pred = pred_df[feature_cols]
    
    # 标准化城市特征
    X_train_normalized, means, stds = normalize_features(X_train, fit=True)
    X_pred_normalized, _, _ = normalize_features(X_pred, means, stds, fit=False)
    
    # 根据SKU类型选择模型（使用GradientBoosting最优配置）
    if sku_type == 'dm':
        model = GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42)
    else:
        model = GradientBoostingRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, random_state=42)
    
    model.fit(X_train_normalized, y_train)
    y_pred = model.predict(X_pred)
    
    # 后处理
    y_pred = np.maximum(y_pred, 0)
    
    # 周末效应调整
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

# ========== 实验二：加入城市特征的预测 ==========
def experiment_2_forecast(history, history_dates, pred_dates, sku_type, city_name, df_loc):
    """
    实验二：加入城市特征的预测
    使用时间特征 + 城市特征
    """
    # 时间特征
    history_df = create_time_features(history_dates)
    history_df['demand'] = history
    
    pred_df = create_time_features(pred_dates)
    
    # 城市特征
    city_features = create_city_features(city_name, df_loc, history_dates)
    for key, value in city_features.items():
        history_df[key] = value
    
    city_features_pred = create_city_features(city_name, df_loc, pred_dates)
    for key, value in city_features_pred.items():
        pred_df[key] = value
    
    # 特征列
    time_features = ['time_idx', 'day_of_week', 'is_weekend', 'sin_day_of_week', 
                    'cos_day_of_week', 'day_of_month', 'month', 'sin_month', 'cos_month']
    city_features_list = ['Longitude', 'Latitude', 'city_area', 'builtup_area', 
                         'resident_pop', 'gdp', 'pop_density', 'gdp_density']
    feature_cols = time_features + city_features_list
    
    X_train = history_df[feature_cols]
    y_train = history_df['demand']
    X_pred = pred_df[feature_cols]
    
    # 标准化城市特征
    X_train_normalized, means, stds = normalize_features(X_train, fit=True)
    X_pred_normalized, _, _ = normalize_features(X_pred, means, stds, fit=False)
    
    # 根据SKU类型选择模型（使用GradientBoosting最优配置）
    if sku_type == 'dm':
        model = GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42)
    else:
        model = GradientBoostingRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, random_state=42)
    
    model.fit(X_train_normalized, y_train)
    y_pred = model.predict(X_pred_normalized)
    
    # 后处理
    y_pred = np.maximum(y_pred, 0)
    
    # 周末效应调整
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

# 执行预测
print("\n开始执行对比实验...")
print("-" * 60)

predictions_exp1 = []  # 实验一结果
predictions_exp2 = []  # 实验二结果

for idx, row in df_past_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    
    history = row.iloc[2:].values.astype(float)
    
    # 实验一：纯时间序列预测
    try:
        y_pred_exp1 = experiment_1_forecast(history, dates, pred_dates, sku)
    except Exception as e:
        print(f"实验一预测 {store}-{sku} 出错: {e}")
        y_pred_exp1 = np.full(7, np.mean(history))
    
    # 实验二：加入城市特征
    try:
        y_pred_exp2 = experiment_2_forecast(history, dates, pred_dates, sku, store, df_loc)
    except Exception as e:
        print(f"实验二预测 {store}-{sku} 出错: {e}")
        y_pred_exp2 = np.full(7, np.mean(history))
    
    predictions_exp1.append([store, sku] + y_pred_exp1.tolist())
    predictions_exp2.append([store, sku] + y_pred_exp2.tolist())
    
    if (idx + 1) % 50 == 0:
        print(f"已完成 {idx + 1}/{len(df_past_order)} 条预测")

# 创建预测结果DataFrame
columns = ['Customer', 'SKU'] + pred_date_strings
predictions_exp1_df = pd.DataFrame(predictions_exp1, columns=columns)
predictions_exp2_df = pd.DataFrame(predictions_exp2, columns=columns)

# 保存预测结果
output_path_exp1 = os.path.join(output_dir, '订单需求量预测结果_实验一_纯时间序列.csv')
output_path_exp2 = os.path.join(output_dir, '订单需求量预测结果_实验二_加入城市特征.csv')

predictions_exp1_df.to_csv(output_path_exp1, index=False)
predictions_exp2_df.to_csv(output_path_exp2, index=False)

print(f"\n实验一结果已保存到: {output_path_exp1}")
print(f"实验二结果已保存到: {output_path_exp2}")

# ========== 评估对比分析 ==========
print("\n" + "=" * 60)
print("实验一与实验二对比评估")
print("=" * 60)

# 计算评估指标
def evaluate_predictions(df_past_order, predictions_df, dates):
    """计算预测评估指标"""
    rmse_list = []
    mape_list = []
    
    for idx, row in df_past_order.iterrows():
        sku = row['SKU']
        history = row.iloc[2:].values.astype(float)
        pred = predictions_df.iloc[idx].iloc[2:].values.astype(float)
        
        # 计算RMSE
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

# 计算两个实验的评估指标
rmse_exp1, mape_exp1, rmse_list_exp1, mape_list_exp1 = evaluate_predictions(df_past_order, predictions_exp1_df, dates)
rmse_exp2, mape_exp2, rmse_list_exp2, mape_list_exp2 = evaluate_predictions(df_past_order, predictions_exp2_df, dates)

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

results_exp1 = evaluate_by_sku_type(df_past_order, predictions_exp1_df, dates)
results_exp2 = evaluate_by_sku_type(df_past_order, predictions_exp2_df, dates)

# 输出评估结果
print(f"\n{'='*60}")
print(f"{'评估指标':<20}{'实验一(纯时间序列)':<25}{'实验二(加入城市特征)':<25}{'改善效果':<15}")
print(f"{'='*60}")

# 总体指标
print(f"{'总体RMSE':<20}{rmse_exp1:<25.4f}{rmse_exp2:<25.4f}{(rmse_exp1-rmse_exp2)/rmse_exp1*100:>+.2f}%")
print(f"{'总体MAPE':<20}{mape_exp1:<25.4f}{mape_exp2:<25.4f}{(mape_exp1-mape_exp2)/mape_exp1*100:>+.2f}%")

# DM类指标
print(f"{'DM类RMSE':<20}{results_exp1['dm']['rmse']:<25.4f}{results_exp2['dm']['rmse']:<25.4f}{(results_exp1['dm']['rmse']-results_exp2['dm']['rmse'])/results_exp1['dm']['rmse']*100:>+.2f}%")
print(f"{'DM类MAPE':<20}{results_exp1['dm']['mape']:<25.4f}{results_exp2['dm']['mape']:<25.4f}{(results_exp1['dm']['mape']-results_exp2['dm']['mape'])/results_exp1['dm']['mape']*100:>+.2f}%")

# IM类指标
print(f"{'IM类RMSE':<20}{results_exp1['im']['rmse']:<25.4f}{results_exp2['im']['rmse']:<25.4f}{(results_exp1['im']['rmse']-results_exp2['im']['rmse'])/results_exp1['im']['rmse']*100:>+.2f}%")
print(f"{'IM类MAPE':<20}{results_exp1['im']['mape']:<25.4f}{results_exp2['im']['mape']:<25.4f}{(results_exp1['im']['mape']-results_exp2['im']['mape'])/results_exp1['im']['mape']*100:>+.2f}%")

# 改善率统计
improvement_rate = []
for i in range(len(rmse_list_exp1)):
    if rmse_list_exp1[i] > 0:
        improvement = (rmse_list_exp1[i] - rmse_list_exp2[i]) / rmse_list_exp1[i] * 100
        improvement_rate.append(improvement)

print(f"\n{'='*60}")
print(f"改善率统计:")
print(f"  - 平均改善率: {np.mean(improvement_rate):.2f}%")
print(f"  - 改善的预测数量: {sum(1 for x in improvement_rate if x > 0)}/{len(improvement_rate)}")
print(f"  - 最佳改善率: {max(improvement_rate):.2f}%")
print(f"  - 最差改善率: {min(improvement_rate):.2f}%")

# Visualization Comparison
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Scientific color palette
colors_scientific = {
    'exp1': '#4472C4',  # Blue
    'exp2': '#ED7D31',  # Orange
    'improvement': '#70AD47',  # Green
    'neutral': '#A5A5A5'  # Gray
}

# 1. RMSE Distribution Comparison
ax1 = axes[0, 0]
ax1.hist(rmse_list_exp1, bins=30, alpha=0.75, label='Experiment 1 (Time Series Only)', color=colors_scientific['exp1'], edgecolor='black', linewidth=0.5)
ax1.hist(rmse_list_exp2, bins=30, alpha=0.75, label='Experiment 2 (With City Features)', color=colors_scientific['exp2'], edgecolor='black', linewidth=0.5)
ax1.set_xlabel('RMSE', fontsize=12, fontweight='bold')
ax1.set_ylabel('Frequency', fontsize=12, fontweight='bold')
ax1.set_title('RMSE Distribution Comparison', fontsize=13, fontweight='bold')
ax1.legend(loc='upper right', fontsize=10)
ax1.tick_params(axis='both', labelsize=10)
ax1.grid(True, alpha=0.3, linestyle='--')

# 2. MAPE Distribution Comparison
ax2 = axes[0, 1]
ax2.hist(mape_list_exp1, bins=30, alpha=0.75, label='Experiment 1 (Time Series Only)', color=colors_scientific['exp1'], edgecolor='black', linewidth=0.5)
ax2.hist(mape_list_exp2, bins=30, alpha=0.75, label='Experiment 2 (With City Features)', color=colors_scientific['exp2'], edgecolor='black', linewidth=0.5)
ax2.set_xlabel('MAPE (%)', fontsize=12, fontweight='bold')
ax2.set_ylabel('Frequency', fontsize=12, fontweight='bold')
ax2.set_title('MAPE Distribution Comparison', fontsize=13, fontweight='bold')
ax2.legend(loc='upper right', fontsize=10)
ax2.tick_params(axis='both', labelsize=10)
ax2.grid(True, alpha=0.3, linestyle='--')

# 3. RMSE by SKU Type
ax3 = axes[1, 0]
x = np.arange(2)
width = 0.35
rmse_values = [results_exp1['dm']['rmse'], results_exp1['im']['rmse']]
rmse_values2 = [results_exp2['dm']['rmse'], results_exp2['im']['rmse']]

bars1 = ax3.bar(x - width/2, rmse_values, width, label='Experiment 1 (Time Series Only)', 
                color=colors_scientific['exp1'], alpha=0.85, edgecolor='black', linewidth=0.5)
bars2 = ax3.bar(x + width/2, rmse_values2, width, label='Experiment 2 (With City Features)', 
                color=colors_scientific['exp2'], alpha=0.85, edgecolor='black', linewidth=0.5)

ax3.set_xlabel('SKU Type', fontsize=12, fontweight='bold')
ax3.set_ylabel('RMSE', fontsize=12, fontweight='bold')
ax3.set_title('RMSE Comparison by SKU Type', fontsize=13, fontweight='bold')
ax3.set_xticks(x)
ax3.set_xticklabels(['DM (Dry Goods)', 'IM (Fresh Goods)'], fontsize=11)
ax3.legend(loc='upper right', fontsize=10)
ax3.tick_params(axis='y', labelsize=10)
ax3.grid(True, alpha=0.3, linestyle='--', axis='y')

# 4. Improvement Rate Distribution
ax4 = axes[1, 1]
ax4.hist(improvement_rate, bins=30, color=colors_scientific['improvement'], alpha=0.75, edgecolor='black', linewidth=0.5)
ax4.axvline(x=0, color='#C00000', linestyle='--', linewidth=2, label='No Improvement Threshold')
ax4.set_xlabel('Improvement Rate (%)', fontsize=12, fontweight='bold')
ax4.set_ylabel('Frequency', fontsize=12, fontweight='bold')
ax4.set_title('Improvement Rate Distribution (Exp2 vs Exp1)', fontsize=13, fontweight='bold')
ax4.legend(loc='upper right', fontsize=10)
ax4.tick_params(axis='both', labelsize=10)
ax4.grid(True, alpha=0.3, linestyle='--')

# Add mean improvement line
mean_improvement = np.mean(improvement_rate)
ax4.axvline(x=mean_improvement, color='#FFC000', linestyle='-', linewidth=2, label=f'Mean: {mean_improvement:.2f}%')
ax4.legend(loc='upper right', fontsize=9)

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'city_feature_comparison.png'), dpi=300, bbox_inches='tight', facecolor='white')
plt.close()

print(f"\nVisualization saved to: {os.path.join(output_dir, 'city_feature_comparison.png')}")

# 生成详细报告
report = f"""
# 实验对比报告：城市特征对预测效果的影响

## 实验设计

### 实验一：纯时间序列预测（现有方法）
- **特征**: 时间特征（星期几、是否周末、时间索引、月份等）
- **模型**: 随机森林回归（根据SKU类型调整参数）

### 实验二：加入城市特征预测
- **特征**: 时间特征 + 城市特征（经纬度、城市面积、人口、GDP等）
- **模型**: 随机森林回归（根据SKU类型调整参数）

## 评估结果

### 总体评估指标

| 指标 | 实验一(纯时间序列) | 实验二(加入城市特征) | 改善率 |
|------|-------------------|---------------------|--------|
| RMSE | {rmse_exp1:.4f} | {rmse_exp2:.4f} | {(rmse_exp1-rmse_exp2)/rmse_exp1*100:+.2f}% |
| MAPE | {mape_exp1:.4f}% | {mape_exp2:.4f}% | {(mape_exp1-mape_exp2)/mape_exp1*100:+.2f}% |

### 按SKU类型评估

| SKU类型 | 指标 | 实验一 | 实验二 | 改善率 |
|---------|------|--------|--------|--------|
| DM(干货类) | RMSE | {results_exp1['dm']['rmse']:.4f} | {results_exp2['dm']['rmse']:.4f} | {(results_exp1['dm']['rmse']-results_exp2['dm']['rmse'])/results_exp1['dm']['rmse']*100:+.2f}% |
| DM(干货类) | MAPE | {results_exp1['dm']['mape']:.4f}% | {results_exp2['dm']['mape']:.4f}% | {(results_exp1['dm']['mape']-results_exp2['dm']['mape'])/results_exp1['dm']['mape']*100:+.2f}% |
| IM(鲜活类) | RMSE | {results_exp1['im']['rmse']:.4f} | {results_exp2['im']['rmse']:.4f} | {(results_exp1['im']['rmse']-results_exp2['im']['rmse'])/results_exp1['im']['rmse']*100:+.2f}% |
| IM(鲜活类) | MAPE | {results_exp1['im']['mape']:.4f}% | {results_exp2['im']['mape']:.4f}% | {(results_exp1['im']['mape']-results_exp2['im']['mape'])/results_exp1['im']['mape']*100:+.2f}% |

### 改善率统计

- 平均改善率: {np.mean(improvement_rate):.2f}%
- 改善的预测数量: {sum(1 for x in improvement_rate if x > 0)}/{len(improvement_rate)} ({sum(1 for x in improvement_rate if x > 0)/len(improvement_rate)*100:.1f}%)
- 最佳改善率: {max(improvement_rate):.2f}%
- 最差改善率: {min(improvement_rate):.2f}%

## 结论

{'✅ 加入城市特征后预测效果有明显改善' if np.mean(improvement_rate) > 0 else '❌ 加入城市特征后预测效果没有明显改善'}

"""

# 保存报告
report_path = os.path.join(output_dir, '实验对比报告_城市特征影响.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\n详细报告已保存到: {report_path}")
print(report)

print("\n实验对比完成！")