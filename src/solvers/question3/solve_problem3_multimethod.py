"""
对应论文文档: 问题3.md （文件: 问题3.md）
该脚本: 多方法对比（RandomForest, GradientBoosting, SVR, MLP, LightGBM 等）
公式/说明对照:
    - 预测对象 y_{t} 的表达与目标 H 步预测（参见问题3.md 中的符号段）
    - 评价指标: RMSE = \sqrt{\frac{1}{N}\sum (y-\hat y)^2}, MAPE = \frac{100\%}{N}\sum |(y-\hat y)/y|

实现提示:
    - 使用 TimeSeriesSplit 进行时序 CV，GridSearchCV 用于超参数搜索（避免时间序列数据泄露）
    - 记录每次实验的随机种子、特征标准化参数与模型配置以保证可复现
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
import warnings
import os

# Try to import LightGBM, fall back to sklearn if not available
try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
    print("✓ LightGBM 已加载")
except ImportError:
    HAS_LIGHTGBM = False
    print("⚠ LightGBM 未安装，将使用sklearn的HistGradientBoostingRegressor作为替代")

warnings.filterwarnings('ignore')

print("=" * 70)
print("多方法对比实验：问题三预测模型综合评估")
print("=" * 70)

# 创建输出目录
output_dir = str(_REPO_ROOT / 'results/question3')
os.makedirs(output_dir, exist_ok=True)

# 读取数据
df_past_order = pd.read_csv(str(_REPO_ROOT / 'data/raw/df_past_order.csv'))
df_loc = pd.read_csv(str(_REPO_ROOT / 'data/raw/df_loc.csv'))
print(f"历史订单数据: {df_past_order.shape}")
print(f"城市信息数据: {df_loc.shape}")

# 数据预处理
dates = pd.to_datetime(df_past_order.columns[2:], format='%Y/%m/%d')
pred_dates = pd.date_range(start='2016-06-24', end='2016-06-30', freq='D')
pred_date_strings = [d.strftime('%Y/%m/%d') for d in pred_dates]

# ========== 特征工程 ==========
def create_time_features(ts_dates):
    """创建时间特征"""
    df = pd.DataFrame({'date': ts_dates})
    df['day_of_week'] = df['date'].dt.dayofweek
    df['day_of_month'] = df['date'].dt.day
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['sin_day_of_week'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['cos_day_of_week'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['time_idx'] = np.arange(len(df))
    df['month'] = df['date'].dt.month
    df['sin_month'] = np.sin(2 * np.pi * df['month'] / 12)
    df['cos_month'] = np.cos(2 * np.pi * df['month'] / 12)
    return df

def get_city_features(city_name, df_loc):
    """获取城市特征"""
    city_data = df_loc[df_loc['Location'].str.lower() == city_name.lower()]
    if city_data.empty:
        city_data = df_loc[df_loc['Location'].str.lower().str.contains(city_name.lower().split('-')[0])]
    if city_data.empty:
        return {
            'Longitude': 116.4, 'Latitude': 39.9, 'city_area': 10000,
            'builtup_area': 500, 'resident_pop': 500, 'gdp': 5000
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

def create_all_features(city_name, df_loc, ts_dates, include_city=True):
    """创建所有特征"""
    df = create_time_features(ts_dates)
    if include_city:
        city_data = get_city_features(city_name, df_loc)
        for key, value in city_data.items():
            df[key] = value
        # 派生特征
        df['pop_density'] = df['resident_pop'] / df['city_area'] * 1000
        df['gdp_density'] = df['gdp'] / df['city_area']
    return df

# ========== 超参数网格 ==========
PARAM_GRIDS = {
    'RandomForest': {
        'n_estimators': [50, 100, 150],
        'max_depth': [3, 5, 7, 10],
        'min_samples_split': [2, 5],
        'min_samples_leaf': [1, 2]
    },
    'GradientBoosting': {
        'n_estimators': [50, 100, 150],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
        'subsample': [0.8, 1.0]
    },
    'SVR': {
        'kernel': ['rbf', 'linear'],
        'C': [0.1, 1, 10],
        'epsilon': [0.01, 0.1, 0.5]
    },
    'MLP': {
        'hidden_layer_sizes': [(50,), (100,), (50, 50)],
        'activation': ['relu', 'tanh'],
        'alpha': [0.0001, 0.001, 0.01],
        'learning_rate': ['constant', 'adaptive']
    }
}

# LightGBM参数网格（如果可用）
if HAS_LIGHTGBM:
    PARAM_GRIDS['LightGBM'] = {
        'n_estimators': [50, 100, 150],
        'max_depth': [3, 5, 7, -1],  # -1表示无限制
        'learning_rate': [0.01, 0.05, 0.1],
        'num_leaves': [15, 31, 50],
        'subsample': [0.8, 1.0]
    }

# ========== 预测方法 ==========
class TimeSeriesPredictor:
    """时间序列预测器基类"""
    
    def __init__(self, method='RandomForest', sku_type='dm', include_city=True):
        self.method = method
        self.sku_type = sku_type
        self.include_city = include_city
        self.model = None
        self.scaler = StandardScaler()
        self.best_params = {}
        
    def get_base_model(self, params=None):
        """获取基础模型"""
        if params is None:
            # 默认参数（基于问题特性选择）
            if self.method == 'RandomForest':
                if self.sku_type == 'dm':
                    return RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
                else:
                    return RandomForestRegressor(n_estimators=150, max_depth=7, random_state=42)
            elif self.method == 'GradientBoosting':
                if self.sku_type == 'dm':
                    return GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42)
                else:
                    return GradientBoostingRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, random_state=42)
            elif self.method == 'SVR':
                return SVR(kernel='rbf', C=1, epsilon=0.1)
            elif self.method == 'MLP':
                if self.sku_type == 'dm':
                    return MLPRegressor(hidden_layer_sizes=(100,), max_iter=500, random_state=42)
                else:
                    return MLPRegressor(hidden_layer_sizes=(100, 50), max_iter=500, random_state=42)
            elif self.method == 'LightGBM' and HAS_LIGHTGBM:
                if self.sku_type == 'dm':
                    return lgb.LGBMRegressor(n_estimators=100, max_depth=5, learning_rate=0.05, random_state=42, verbose=-1)
                else:
                    return lgb.LGBMRegressor(n_estimators=150, max_depth=7, learning_rate=0.1, random_state=42, verbose=-1)
        else:
            # 使用优化后的参数
            if self.method == 'RandomForest':
                return RandomForestRegressor(**params, random_state=42)
            elif self.method == 'GradientBoosting':
                return GradientBoostingRegressor(**params, random_state=42)
            elif self.method == 'SVR':
                return SVR(**params)
            elif self.method == 'MLP':
                return MLPRegressor(**params, max_iter=500, random_state=42)
            elif self.method == 'LightGBM' and HAS_LIGHTGBM:
                return lgb.LGBMRegressor(**params, random_state=42, verbose=-1)
    
    def tune_hyperparameters(self, X, y):
        """超参数调优（网格搜索 + 时间序列交叉验证）"""
        print(f"\n  开始超参数调优 ({self.method})...")
        
        model = self.get_base_model()
        param_grid = PARAM_GRIDS.get(self.method, {})
        
        if not param_grid:
            return
        
        # 时间序列交叉验证
        tscv = TimeSeriesSplit(n_splits=3)
        
        # 简化参数网格以加速
        reduced_grid = {}
        for key, values in list(param_grid.items())[:2]:  # 只调优最重要的2个参数
            reduced_grid[key] = values
        
        try:
            grid_search = GridSearchCV(
                model, reduced_grid, 
                cv=tscv, 
                scoring='neg_root_mean_squared_error',
                n_jobs=-1,
                verbose=0
            )
            grid_search.fit(X, y)
            self.best_params = grid_search.best_params_
            print(f"  最佳参数: {self.best_params}")
        except Exception as e:
            print(f"  超参数调优失败: {e}")
            self.best_params = {}
    
    def fit_predict(self, history, history_dates, pred_dates, city_name, df_loc):
        """训练和预测"""
        # 创建特征
        history_df = create_all_features(city_name, df_loc, history_dates, self.include_city)
        pred_df = create_all_features(city_name, df_loc, pred_dates, self.include_city)
        
        # 添加需求数据到特征DataFrame
        history_df['demand'] = history
        
        # 排除非特征列
        feature_cols = [col for col in history_df.columns if col not in ['date', 'demand']]
        
        X_train = history_df[feature_cols].values
        y_train = history_df['demand'].values
        X_pred = pred_df[feature_cols].values
        
        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_pred_scaled = self.scaler.transform(X_pred)
        
        # 超参数调优（每50个样本做一次，避免太慢）
        if hasattr(self, '_tune_count'):
            self._tune_count += 1
        else:
            self._tune_count = 1
        
        if self._tune_count % 50 == 0:
            self.tune_hyperparameters(X_train_scaled, y_train)
        
        # 训练模型
        self.model = self.get_base_model(self.best_params)
        self.model.fit(X_train_scaled, y_train)
        
        # 预测
        y_pred = self.model.predict(X_pred_scaled)
        
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

# ========== 主实验 ==========
print("\n" + "=" * 70)
print("开始多方法对比实验")
print("=" * 70)

# 定义实验方法（包含LightGBM）
methods = ['RandomForest', 'GradientBoosting', 'SVR', 'MLP']
if HAS_LIGHTGBM:
    methods.append('LightGBM')

results = {method: {'rmse': [], 'mape': [], 'predictions': []} for method in methods}

# 创建预测器
predictors = {method: TimeSeriesPredictor(method=method, sku_type='dm') for method in methods}

for idx, row in df_past_order.iterrows():
    store = row['Name']
    sku = row['SKU']
    history = row.iloc[2:].values.astype(float)
    
    # 更新预测器的SKU类型
    for method in methods:
        predictors[method].sku_type = sku
    
    for method in methods:
        try:
            y_pred = predictors[method].fit_predict(history, dates, pred_dates, store, df_loc)
            results[method]['predictions'].append([store, sku] + y_pred.tolist())
        except Exception as e:
            print(f"  {method} 预测 {store}-{sku} 出错: {e}")
            y_pred = np.full(7, np.mean(history))
            results[method]['predictions'].append([store, sku] + y_pred.tolist())
    
    if (idx + 1) % 30 == 0:
        print(f"已完成 {idx + 1}/{len(df_past_order)} 条")

# ========== 评估结果 ==========
print("\n" + "=" * 70)
print("评估结果汇总")
print("=" * 70)

def evaluate_method(df_past_order, predictions_df):
    """评估单个方法的性能"""
    rmse_list = []
    mape_list = []
    
    for idx, row in df_past_order.iterrows():
        history = row.iloc[2:].values.astype(float)
        pred = predictions_df.iloc[idx].iloc[2:].values.astype(float)
        
        rmse = np.sqrt(mean_squared_error(history[-7:], pred))
        rmse_list.append(rmse)
        
        mask = history[-7:] != 0
        if mask.sum() > 0:
            mape = mean_absolute_percentage_error(history[-7:][mask], pred[mask]) * 100
            mape_list.append(mape)
        else:
            mape_list.append(0)
    
    return {
        'rmse_mean': np.mean(rmse_list),
        'rmse_std': np.std(rmse_list),
        'mape_mean': np.mean(mape_list),
        'mape_std': np.std(mape_list),
        'rmse_list': rmse_list,
        'mape_list': mape_list
    }

# 按SKU类型分组评估
def evaluate_by_sku(df_past_order, predictions_df):
    """按SKU类型评估"""
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

# 计算各方法的评估指标
method_evaluations = {}
columns = ['Customer', 'SKU'] + pred_date_strings

for method in methods:
    predictions_df = pd.DataFrame(results[method]['predictions'], columns=columns)
    method_evaluations[method] = {
        'overall': evaluate_method(df_past_order, predictions_df),
        'by_sku': evaluate_by_sku(df_past_order, predictions_df)
    }
    
    # 保存结果
    output_path = os.path.join(output_dir, f'预测结果_{method}.csv')
    predictions_df.to_csv(output_path, index=False)

# 打印评估结果
print(f"\n{'方法':<25}{'RMSE均值':<12}{'RMSE标准差':<12}{'MAPE均值':<12}{'MAPE标准差':<12}")
print("-" * 70)

best_rmse = float('inf')
best_method = None

for method in methods:
    eval_result = method_evaluations[method]['overall']
    print(f"{method:<25}{eval_result['rmse_mean']:<12.4f}{eval_result['rmse_std']:<12.4f}"
          f"{eval_result['mape_mean']:<12.4f}{eval_result['mape_std']:<12.4f}")
    
    if eval_result['rmse_mean'] < best_rmse:
        best_rmse = eval_result['rmse_mean']
        best_method = method

print(f"\n🏆 最佳方法（按RMSE）: {best_method} (RMSE: {best_rmse:.4f})")

# ========== Visualization ==========
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Scientific color palette - extended for 5 methods
# Blue, Orange, Green, Gray, Purple - commonly used in academic publications
colors = ['#4472C4', '#ED7D31', '#70AD47', '#A5A5A5', '#7030A0']

# 1. RMSE Comparison (with error bars)
ax1 = axes[0, 0]
methods_names = list(method_evaluations.keys())
rmse_means = [method_evaluations[m]['overall']['rmse_mean'] for m in methods_names]
rmse_stds = [method_evaluations[m]['overall']['rmse_std'] for m in methods_names]

bars = ax1.bar(methods_names, rmse_means, yerr=rmse_stds, capsize=5, color=colors[:len(methods_names)], alpha=0.85, edgecolor='black', linewidth=0.5)
ax1.set_ylabel('RMSE', fontsize=12, fontweight='bold')
ax1.set_title('RMSE Comparison Across Methods\n(Lower is Better)', fontsize=13, fontweight='bold')
ax1.tick_params(axis='x', rotation=30, labelsize=10)
ax1.tick_params(axis='y', labelsize=10)
ax1.grid(True, alpha=0.3, linestyle='--')

# Highlight best method
best_idx = rmse_means.index(min(rmse_means))
bars[best_idx].set_color('#FFC000')
bars[best_idx].set_edgecolor('black')
bars[best_idx].set_linewidth(2)

# 2. MAPE Comparison (with error bars)
ax2 = axes[0, 1]
mape_means = [method_evaluations[m]['overall']['mape_mean'] for m in methods_names]
mape_stds = [method_evaluations[m]['overall']['mape_std'] for m in methods_names]

bars = ax2.bar(methods_names, mape_means, yerr=mape_stds, capsize=5, color=colors[:len(methods_names)], alpha=0.85, edgecolor='black', linewidth=0.5)
ax2.set_ylabel('MAPE (%)', fontsize=12, fontweight='bold')
ax2.set_title('MAPE Comparison Across Methods\n(Lower is Better)', fontsize=13, fontweight='bold')
ax2.tick_params(axis='x', rotation=30, labelsize=10)
ax2.tick_params(axis='y', labelsize=10)
ax2.grid(True, alpha=0.3, linestyle='--')

# Highlight best method
best_idx = mape_means.index(min(mape_means))
bars[best_idx].set_color('#FFC000')
bars[best_idx].set_edgecolor('black')
bars[best_idx].set_linewidth(2)

# 3. RMSE by SKU Type
ax3 = axes[1, 0]
x = np.arange(len(methods_names))
width = 0.35

dm_rmse = [method_evaluations[m]['by_sku']['dm']['rmse'] for m in methods_names]
im_rmse = [method_evaluations[m]['by_sku']['im']['rmse'] for m in methods_names]

bars1 = ax3.bar(x - width/2, dm_rmse, width, label='DM (Dry Goods)', color='#4472C4', alpha=0.85, edgecolor='black', linewidth=0.5)
bars2 = ax3.bar(x + width/2, im_rmse, width, label='IM (Fresh Goods)', color='#ED7D31', alpha=0.85, edgecolor='black', linewidth=0.5)
ax3.set_ylabel('RMSE', fontsize=12, fontweight='bold')
ax3.set_title('RMSE Comparison by SKU Type', fontsize=13, fontweight='bold')
ax3.set_xticks(x)
ax3.set_xticklabels(methods_names, rotation=30, ha='right', fontsize=10)
ax3.legend(loc='upper right', fontsize=10)
ax3.tick_params(axis='y', labelsize=10)
ax3.grid(True, alpha=0.3, linestyle='--', axis='y')

# 4. RMSE Distribution (Box Plot)
ax4 = axes[1, 1]
rmse_data = [method_evaluations[m]['overall']['rmse_list'] for m in methods_names]
bp = ax4.boxplot(rmse_data, labels=methods_names, patch_artist=True, notch=False)

for patch, color in zip(bp['boxes'], colors[:len(methods_names)]):
    patch.set_facecolor(color)
    patch.set_alpha(0.75)
    patch.set_edgecolor('black')
    patch.set_linewidth(1)

for median in bp['medians']:
    median.set_color('black')
    median.set_linewidth(2)

ax4.set_ylabel('RMSE', fontsize=12, fontweight='bold')
ax4.set_title('RMSE Distribution Across Methods', fontsize=13, fontweight='bold')
ax4.tick_params(axis='x', rotation=30, labelsize=10)
ax4.tick_params(axis='y', labelsize=10)
ax4.grid(True, alpha=0.3, linestyle='--', axis='y')

plt.tight_layout()
plt.savefig(os.path.join(output_dir, 'multimethod_comparison.png'), dpi=300, bbox_inches='tight', facecolor='white')
plt.close()

print(f"\nVisualization saved to: {os.path.join(output_dir, 'multimethod_comparison.png')}")

# ========== 生成详细报告 ==========
report = f"""
# 多方法对比实验报告：问题三预测模型综合评估

## 实验概述

本实验对比了4种机器学习方法的预测效果：
1. **RandomForest（随机森林）** - 现有方法，集成多棵决策树
2. **GradientBoosting（梯度提升）** - 序列化构建决策树
3. **SVR（支持向量回归）** - 基于核函数的回归方法
4. **MLP（多层感知机）** - 深度学习前馈神经网络

## 超参数选择策略

### 当前超参数选择依据：
基于问题特性（SKU类型差异化）进行手动调优：

| SKU类型 | 随机森林参数 | 梯度提升参数 | 特点 |
|---------|-------------|-------------|------|
| **DM(干货类)** | n_estimators=100, max_depth=5 | n_estimators=100, max_depth=5, lr=0.05 | 需求稳定，模型简单 |
| **IM(鲜活类)** | n_estimators=150, max_depth=7 | n_estimators=150, max_depth=7, lr=0.1 | 需求波动，模型复杂 |

### 超参数优化策略：
- 使用**时间序列交叉验证**（TimeSeriesSplit）避免数据泄露
- 采用**网格搜索**（GridSearchCV）寻找最优参数
- 主要调优参数：树深度、学习率、估计器数量等

## 评估结果

### 总体性能对比

| 方法 | RMSE均值 | RMSE标准差 | MAPE均值 | MAPE标准差 |
|------|---------|-----------|---------|-----------|
"""

for method in methods_names:
    eval_result = method_evaluations[method]['overall']
    report += f"| {method} | {eval_result['rmse_mean']:.4f} | {eval_result['rmse_std']:.4f} | {eval_result['mape_mean']:.4f}% | {eval_result['mape_std']:.4f}% |\n"

report += f"""
### 按SKU类型性能对比

| 方法 | DM类RMSE | DM类MAPE | IM类RMSE | IM类MAPE |
|------|---------|---------|---------|---------|
"""

for method in methods_names:
    by_sku = method_evaluations[method]['by_sku']
    report += f"| {method} | {by_sku['dm']['rmse']:.4f} | {by_sku['dm']['mape']:.4f}% | {by_sku['im']['rmse']:.4f} | {by_sku['im']['mape']:.4f}% |\n"

report += f"""
## 结论与建议

### 🏆 最佳方法
基于RMSE评估，**{best_method}** 表现最佳（RMSE: {best_rmse:.4f}）

### 方法特点分析

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| RandomForest | 稳定、抗过拟合、训练快 | 对时间序列捕捉有限 | 基线模型 |
| GradientBoosting | 精度高、可处理复杂模式 | 容易过拟合、训练慢 | 高精度需求 |
| SVR | 对小样本友好、泛化能力强 | 对大数据量效率低 | 小样本场景 |
| MLP | 能学习复杂非线性关系 | 需要大量数据、解释性差 | 复杂模式识别 |

### 💡 建议
1. **基线模型**：使用 RandomForest 作为快速基线
2. **高精度需求**：考虑 GradientBoosting 或集成方法
3. **后续优化**：可以尝试模型融合（Ensemble）

## 输出文件

- 预测结果文件：`预测结果_{method}.csv` （各方法）
- 可视化对比图：`多方法对比_预测性能分析.png`
- 本报告：`多方法对比报告.md`
"""

# 保存报告
report_path = os.path.join(output_dir, '多方法对比报告.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report)

print(f"\n详细报告已保存到: {report_path}")

# ========== 超参数优化详情 ==========
print("\n" + "=" * 70)
print("超参数优化详情")
print("=" * 70)

print("""
### 随机森林（RandomForest）
- **n_estimators**: 树的数量 [50, 100, 150]
  - 更多树通常提高稳定性，但增加计算时间
  - 问题三数据量适中，100-150棵足够
- **max_depth**: 树的最大深度 [3, 5, 7, 10]
  - DM类（干货）：需求稳定，深度5足够
  - IM类（鲜活）：需求波动，深度7更好
- **min_samples_split/leaf**: 防止过拟合

### 梯度提升（GradientBoosting）
- **n_estimators**: 迭代次数
- **max_depth**: 单棵树深度，通常3-7
- **learning_rate**: 学习率 [0.01, 0.05, 0.1]
  - 小学习率需要更多迭代，但更稳定
- **subsample**: 子采样比例，防止过拟合

### 支持向量回归（SVR）
- **kernel**: 核函数选择 ['rbf', 'linear']
  - rbf: 捕捉非线性关系
  - linear: 线性关系
- **C**: 正则化参数
- **epsilon**: ε不敏感损失参数

### 多层感知机（MLP）
- **hidden_layer_sizes**: 隐藏层结构 [(50,), (100,), (50,50)]
- **activation**: 激活函数 ['relu', 'tanh']
- **alpha**: L2正则化系数
- **learning_rate**: 学习率策略
""")

print("\n多方法对比实验完成！")







