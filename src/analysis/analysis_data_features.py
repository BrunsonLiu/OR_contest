"""
============================================================
数据特征深度分析脚本
目的：分析问题三的预测数据与历史订单数据，
     寻找周期性、趋势性规律，
     为问题四的不确定集构建提供改进建议
============================================================
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys as _runtime_sys
_runtime_sys.path.insert(0, str(_REPO_ROOT))
from src.runtime import results_root as _results_root, read_forecast as _read_forecast, configure_solver as _configure_solver, record_solver as _record_solver
_RESULTS_ROOT = _results_root()
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os
from scipy import stats
from scipy.signal import find_peaks
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, mean_absolute_error
import warnings
warnings.filterwarnings('ignore')

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = str(_REPO_ROOT)
OUTPUT_DIR = os.path.join(str(_RESULTS_ROOT), 'question3', 'data_feature_analysis')
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 80)
print("=== 数据特征深度分析：周期性、趋势性、残差分布与不确定集改进 ===")
print("=" * 80)

# ============================================================
# 1. 数据加载
# ============================================================
print("\n" + "=" * 80)
print("1. 数据加载与基础统计")
print("=" * 80)

df_past = pd.read_csv(os.path.join(BASE_DIR, 'data/raw', 'df_past_order.csv'))
df_sota = _read_forecast()

# 解析日期
historical_cols = [c for c in df_past.columns if c not in ['Name', 'SKU']]
hist_dates = pd.to_datetime(historical_cols, format='%Y/%m/%d')
print(f"  历史数据：{len(df_past)} 条记录，{len(hist_dates)} 天 ({hist_dates[0].strftime('%Y-%m-%d')} ~ {hist_dates[-1].strftime('%Y-%m-%d')})")

forecast_cols = [c for c in df_sota.columns if c not in ['Customer', 'SKU']]
fc_dates = pd.to_datetime(forecast_cols, format='%Y/%m/%d')
print(f"  预测数据：{len(df_sota)} 条记录，{len(fc_dates)} 天 ({fc_dates[0].strftime('%Y-%m-%d')} ~ {fc_dates[-1].strftime('%Y-%m-%d')})")

# 构建 城市-SKU 到历史序列的映射
history_dict = {}
for _, row in df_past.iterrows():
    key = (row['Name'], row['SKU'])
    vals = row[historical_cols].values.astype(float)
    history_dict[key] = vals

# 构建 城市-SKU 到预测值的映射
forecast_dict = {}
for _, row in df_sota.iterrows():
    key = (row['Customer'], row['SKU'])
    vals = row[forecast_cols].values.astype(float)
    forecast_dict[key] = vals

all_keys = sorted(history_dict.keys())
print(f"  共有 {len(all_keys)} 个城市-SKU 组合")
print(f"  其中 {len(forecast_dict)} 个有预测值")

# 历史数据按天的总量
daily_totals_hist = {s: [] for s in ['dm', 'im']}
for s in ['dm', 'im']:
    for j, date_col in enumerate(historical_cols):
        total = sum(history_dict[k][j] for k in all_keys if k[1] == s)
        daily_totals_hist[s].append(total)
    print(f"  {s} 历史日均总量: {np.mean(daily_totals_hist[s]):.0f} ± {np.std(daily_totals_hist[s]):.0f} 吨")

daily_totals_fc = {s: [] for s in ['dm', 'im']}
for s in ['dm', 'im']:
    for j, date_col in enumerate(forecast_cols):
        total = sum(forecast_dict.get(k, [0]*7)[j] for k in all_keys if k[1] == s)
        daily_totals_fc[s].append(total)
    print(f"  {s} 预测日均总量: {np.mean(daily_totals_fc[s]):.0f} ± {np.std(daily_totals_fc[s]):.0f} 吨")

# ============================================================
# 2. 周期性分析（7天周内周期性）
# ============================================================
print("\n" + "=" * 80)
print("2. 周期性检测 - 7天周内模式")
print("=" * 80)

# 2.1 自相关分析
def compute_acf(series, max_lag=20):
    """计算自相关系数"""
    series = np.array(series)
    n = len(series)
    mean = np.mean(series)
    var = np.var(series)
    if var < 1e-10:
        return np.zeros(max_lag + 1)
    acf = []
    for lag in range(max_lag + 1):
        if lag == 0:
            acf.append(1.0)
        else:
            cov = np.sum((series[:n-lag] - mean) * (series[lag:] - mean)) / n
            acf.append(cov / var)
    return np.array(acf)

# 对每个城市-SKU计算自相关
all_acfs = []
lag7_corrs = []
for key in all_keys:
    vals = history_dict[key]
    acf = compute_acf(vals, max_lag=14)
    all_acfs.append(acf)
    lag7_corrs.append(acf[7] if len(acf) > 7 else 0)

# 统计 lag-7 自相关
lag7_arr = np.array(lag7_corrs)
print(f"\n  历史数据 lag-7 自相关系数统计：")
print(f"    均值: {np.mean(lag7_arr):.4f}")
print(f"    中位数: {np.median(lag7_arr):.4f}")
print(f"    标准差: {np.std(lag7_arr):.4f}")
print(f"    范围: [{np.min(lag7_arr):.4f}, {np.max(lag7_arr):.4f}]")
pct_positive = np.sum(lag7_arr > 0.1) / len(lag7_arr) * 100
pct_strong = np.sum(lag7_arr > 0.3) / len(lag7_arr) * 100
print(f"    lag-7 > 0.1 的比例: {pct_positive:.1f}%")
print(f"    lag-7 > 0.3 (强周期) 的比例: {pct_strong:.1f}%")

# 2.2 逐星期分布分析
print(f"\n  按星期几分组的需求统计 (历史数据)：")
hist_dates_weekday = [d.dayofweek for d in hist_dates]  # 0=Mon, 6=Sun
weekday_demands = {w: [] for w in range(7)}
for key in all_keys:
    vals = history_dict[key]
    for j, wd in enumerate(hist_dates_weekday):
        weekday_demands[wd].append(vals[j])

print(f"  {'星期':<8} {'均值':>10} {'中位数':>10} {'标准差':>10} {'CV':>10}")
print("  " + "-" * 50)
weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
for w in range(7):
    arr = np.array(weekday_demands[w])
    mean_v = np.mean(arr)
    std_v = np.std(arr)
    cv = std_v / mean_v if mean_v > 0 else 0
    print(f"  {weekday_names[w]:<8} {mean_v:>10.2f} {np.median(arr):>10.2f} {std_v:>10.2f} {cv:>10.4f}")

# 2.3 检测峰值日
print(f"\n  每周峰值日检测：")
peak_counts = {w: 0 for w in range(7)}
for key in all_keys:
    vals = history_dict[key]
    # 对每个城市-SKU，找出多周平均值最高的星期
    weeks = len(vals) // 7
    if weeks >= 2:
        weekly_avg = np.zeros(7)
        for w in range(7):
            weekly_avg[w] = np.mean([vals[i] for i in range(w, min(len(vals), weeks*7), 7)])
        peak_day = np.argmax(weekly_avg)
        peak_counts[peak_day] += 1

print(f"  {'星期':<8} {'峰值出现次数':>12} {'占比':>10}")
print("  " + "-" * 35)
total_keys = len(all_keys)
for w in range(7):
    print(f"  {weekday_names[w]:<8} {peak_counts[w]:>12} {peak_counts[w]/total_keys*100:>9.1f}%")

# ============================================================
# 3. 趋势性分析
# ============================================================
print("\n" + "=" * 80)
print("3. 趋势性检测")
print("=" * 80)

# 对每个城市-SKU拟合线性趋势
trend_slopes = []
trend_pvalues = []
trend_significant = 0

for key in all_keys:
    vals = history_dict[key]
    t = np.arange(len(vals)).reshape(-1, 1)
    model = LinearRegression()
    model.fit(t, vals)
    slope = model.coef_[0]
    trend_slopes.append(slope)
    
    # 简单p值（t检验近似）
    y_pred = model.predict(t)
    residuals = vals - y_pred
    n = len(vals)
    if n > 2:
        se = np.sqrt(np.sum(residuals**2) / (n - 2))
        se_slope = se / np.sqrt(np.sum((t - t.mean())**2))
        if se_slope > 1e-10:
            t_stat = slope / se_slope
            p_val = 2 * (1 - stats.t.cdf(abs(t_stat), n - 2))
        else:
            p_val = 1.0
    else:
        p_val = 1.0
    trend_pvalues.append(p_val)
    if p_val < 0.05:
        trend_significant += 1

slope_arr = np.array(trend_slopes)
pval_arr = np.array(trend_pvalues)

print(f"  趋势斜率统计 (吨/天)：")
print(f"    均值: {np.mean(slope_arr):.4f}")
print(f"    中位数: {np.median(slope_arr):.4f}")
print(f"    标准差: {np.std(slope_arr):.4f}")
print(f"    范围: [{np.min(slope_arr):.4f}, {np.max(slope_arr):.4f}]")
print(f"    显著趋势 (p<0.05): {trend_significant}/{len(all_keys)} ({trend_significant/len(all_keys)*100:.1f}%)")
print(f"    正趋势比例: {np.sum(slope_arr > 0)/len(slope_arr)*100:.1f}%")
print(f"    负趋势比例: {np.sum(slope_arr < 0)/len(slope_arr)*100:.1f}%")

# ============================================================
# 4. 预测残差分析（回测法）
# ============================================================
print("\n" + "=" * 80)
print("4. 预测残差分析 - 回测法 (Rolling Backtest)")
print("=" * 80)

# 用前16天预测后7天，模拟真实预测场景
from sklearn.ensemble import RandomForestRegressor

def create_simple_features(ts_dates, include_lag=True):
    """简化的特征工程 (仅数值特征)"""
    df = pd.DataFrame({'date': ts_dates})
    df['day_of_week'] = df['date'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['sin_dow'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
    df['cos_dow'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
    df['time_idx'] = np.arange(len(df))
    # 只保留数值特征，去除date列
    feature_cols = ['day_of_week', 'is_weekend', 'sin_dow', 'cos_dow', 'time_idx']
    return df[feature_cols]

# 回测
all_residuals = []      # 所有残差 (actual - predicted)
all_relative_errors = []  # 相对误差
all_cv_values = []
all_actuals = []
key_residual_stats = {}  # 每个key的残差统计

train_days = 16
test_days = len(hist_dates) - train_days  # 7 days
print(f"  回测设置: 训练 {train_days} 天 (前), 测试 {test_days} 天 (后)")

for key in all_keys:
    vals = history_dict[key]
    train_vals = vals[:train_days]
    test_vals = vals[train_days:]
    
    train_dates_arr = hist_dates[:train_days]
    test_dates_arr = hist_dates[train_days:]
    
    # 训练特征
    X_train = create_simple_features(train_dates_arr)
    X_test = create_simple_features(test_dates_arr)
    
    # 训练
    # 对于波动较大 (CV>0.3) 的序列使用更保守的参数
    cv_val = np.std(train_vals) / np.mean(train_vals) if np.mean(train_vals) > 1e-6 else 0
    all_cv_values.append(cv_val)
    
    if cv_val > 0.3:
        model = RandomForestRegressor(n_estimators=80, max_depth=4, random_state=42)
    else:
        model = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
    
    model.fit(X_train, train_vals)
    pred_vals = model.predict(X_test)
    
    # 残差
    residuals = test_vals - pred_vals
    relative_errors = residuals / (test_vals + 1e-6)
    
    all_residuals.extend(residuals)
    all_relative_errors.extend(relative_errors)
    all_actuals.extend(test_vals)
    
    key_residual_stats[key] = {
        'mean_residual': np.mean(residuals),
        'std_residual': np.std(residuals),
        'mean_abs_residual': np.mean(np.abs(residuals)),
        'cv': cv_val,
        'mean_actual': np.mean(test_vals),
    }

resid_arr = np.array(all_residuals)
relerr_arr = np.array(all_relative_errors)
cv_arr = np.array(all_cv_values)
actual_arr = np.array(all_actuals)

# 残差基本统计
print(f"\n  残差 (actual - predicted) 基本统计:")
print(f"    均值: {np.mean(resid_arr):.4f}")
print(f"    标准差: {np.std(resid_arr):.4f}")
print(f"    中位数: {np.median(resid_arr):.4f}")
print(f"    范围: [{np.min(resid_arr):.4f}, {np.max(resid_arr):.4f}]")
print(f"    偏度: {stats.skew(resid_arr):.4f}")
print(f"    峰度: {stats.kurtosis(resid_arr):.4f}")

# 正态性检验
stat, p_norm = stats.normaltest(resid_arr)
print(f"    D'Agostino-Pearson 正态性检验: stat={stat:.4f}, p={p_norm:.6f}")
print(f"    {'残差近似正态分布' if p_norm > 0.05 else '残差显著偏离正态分布'}")

# 分位数
print(f"\n  残差分位数:")
for q in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
    print(f"    {q}%: {np.percentile(resid_arr, q):.4f}")

# 绝对残差分析
abs_resid = np.abs(resid_arr)
print(f"\n  绝对残差统计:")
print(f"    均值 (MAE): {np.mean(abs_resid):.4f}")
print(f"    中位数: {np.median(abs_resid):.4f}")
print(f"    90%分位数: {np.percentile(abs_resid, 90):.4f}")
print(f"    95%分位数: {np.percentile(abs_resid, 95):.4f}")

# ============================================================
# 5. CV方法 vs 残差方法 对比
# ============================================================
print("\n" + "=" * 80)
print("5. CV方法 vs 残差方法 - 不确定集构建对比")
print("=" * 80)

# 5.1 当前 CV 方法
print(f"\n  5.1 当前方法：基于 CV 的不确定半径")
print(f"    公式: delta = CV × y_hat × alpha")
print(f"    其中 alpha = 0.3")

# 计算所有key的CV
all_cvs_full = []
for key in all_keys:
    vals = history_dict[key]
    mean_v = np.mean(vals)
    std_v = np.std(vals, ddof=0)
    if mean_v > 1e-6:
        all_cvs_full.append(std_v / mean_v)

cv_full_arr = np.array(all_cvs_full)
print(f"\n   历史数据 CV 统计 (全23天):")
print(f"    均值: {np.mean(cv_full_arr):.4f}")
print(f"    中位数: {np.median(cv_full_arr):.4f}")
print(f"    25%分位数: {np.percentile(cv_full_arr, 25):.4f}")
print(f"    75%分位数: {np.percentile(cv_full_arr, 75):.4f}")
print(f"    最小值: {np.min(cv_full_arr):.4f}")
print(f"    最大值: {np.max(cv_full_arr):.4f}")

# 当前delta的含义
alpha = 0.3
ty_delta = np.mean(cv_full_arr) * alpha
print(f"\n    典型不确定半径: mean_CV × alpha = {np.mean(cv_full_arr):.4f} × {alpha} = {ty_delta:.4f}")
print(f"    即: 预测不确定性约为名义需求的 {ty_delta*100:.2f}%")

# 5.2 残差方法
print(f"\n  5.2 基于残差的不确定半径")
print(f"    公式: delta = MAE × beta 或 delta = std_residual × beta")

# 按key计算残差标准差和MAE
resid_stds = []
resid_maes = []
for key in all_keys:
    rd = key_residual_stats[key]
    resid_stds.append(rd['std_residual'])
    resid_maes.append(rd['mean_abs_residual'])

resid_std_arr = np.array(resid_stds)
resid_mae_arr = np.array(resid_maes)

print(f"   回测残差标准差分布:")
print(f"    均值: {np.mean(resid_std_arr):.4f}")
print(f"    中位数: {np.median(resid_std_arr):.4f}")
print(f"    25%分位数: {np.percentile(resid_std_arr, 25):.4f}")
print(f"    75%分位数: {np.percentile(resid_std_arr, 75):.4f}")

print(f"   回测MAE分布:")
print(f"    均值: {np.mean(resid_mae_arr):.4f}")
print(f"    中位数: {np.median(resid_mae_arr):.4f}")

print(f"\n  5.3 CV方法与残差方法的核心差异")
# CV相对比例
cv_to_resid_ratio = []
for key in all_keys:
    rd = key_residual_stats[key]
    cv = rd['cv']
    mean_act = rd['mean_actual']
    resid_std = rd['std_residual'] if rd['std_residual'] > 0 else 1e-6
    # CV-based delta = CV * mean_actual * alpha
    cv_delta = cv * mean_act * alpha
    # Residual-based delta = resid_std * 2 (95% confidence)
    resid_delta_95 = resid_std * 1.96
    ratio = resid_delta_95 / (cv_delta + 1e-6)
    cv_to_resid_ratio.append(ratio)

ratio_arr = np.array(cv_to_resid_ratio)
print(f"    resid_delta(95%) / CV_delta(alpha=0.3) 比值:")
print(f"    均值: {np.mean(ratio_arr):.4f}")
print(f"    中位数: {np.median(ratio_arr):.4f}")
print(f"    < 1 的比例 (残差方法更保守): {np.sum(ratio_arr < 1)/len(ratio_arr)*100:.1f}%")
print(f"    > 1 的比例 (CV方法更保守): {np.sum(ratio_arr > 1)/len(ratio_arr)*100:.1f}%")

# 5.4 不同CV水平下的残差分析
print(f"\n  5.4 CV与残差的关系")
# 把CV分成低、中、高三组
cv_training = np.array([key_residual_stats[k]['cv'] for k in all_keys])
resid_std_by_key = np.array([key_residual_stats[k]['std_residual'] for k in all_keys])
mean_act_by_key = np.array([key_residual_stats[k]['mean_actual'] for k in all_keys])

# 分组
low_cv_mask = cv_training <= np.percentile(cv_training, 33)
mid_cv_mask = (cv_training > np.percentile(cv_training, 33)) & (cv_training <= np.percentile(cv_training, 67))
high_cv_mask = cv_training > np.percentile(cv_training, 67)

for label, mask in [('低CV组', low_cv_mask), ('中CV组', mid_cv_mask), ('高CV组', high_cv_mask)]:
    r_std = resid_std_by_key[mask]
    r_mae = resid_mae_arr[mask]
    ma = mean_act_by_key[mask]
    print(f"    {label}: CV范围=[{cv_training[mask].min():.3f}, {cv_training[mask].max():.3f}]")
    print(f"      平均需求: {np.mean(ma):.1f}, 残差std: {np.mean(r_std):.2f}, "
          f"残差std/需求: {np.mean(r_std/(ma+1e-6))*100:.1f}%")
    print(f"      MAE: {np.mean(r_mae):.2f}, MAE/需求: {np.mean(r_mae/(ma+1e-6))*100:.1f}%")

# ============================================================
# 6. SOTA预测与CV预测的对比
# ============================================================
print("\n" + "=" * 80)
print("6. 多模型预测一致性分析")
print("=" * 80)

# 读取各模型预测
method_files = {
    'SOTA(GradientBoosting)': '订单需求量预测结果文件_sota.csv',
    'RandomForest': '预测结果_RandomForest.csv',
    'SVR': '预测结果_SVR.csv',
    'MLP': '预测结果_MLP.csv',
    'LightGBM': '预测结果_LightGBM.csv',
    'GradientBoosting': '预测结果_GradientBoosting.csv',
}

method_forecasts = {}
for method_name, fname in method_files.items():
    fpath = os.path.join(str(_RESULTS_ROOT), 'question3', fname)
    if os.path.exists(fpath):
        df = pd.read_csv(fpath)
        fc_cols = [c for c in df.columns if c not in ['Customer', 'SKU']]
        fc_dict = {}
        for _, row in df.iterrows():
            key = (row['Customer'], row['SKU'])
            vals = row[fc_cols].values.astype(float)
            fc_dict[key] = vals
        method_forecasts[method_name] = fc_dict
        print(f"  加载 {method_name}: {len(fc_dict)} 条预测")

# 本节需要同实验 question3 目录下的多方法预测网格。统一入口会隔离结果
# 根目录，若这些兄弟文件未随实验提供，本节无输入可比；明确跳过而不是
# 继续到 methods_list[0] 触发 IndexError，避免整个任务无产物。
methods_list = list(method_forecasts.keys())
if not method_forecasts:
    print(f"  未找到多方法预测文件（在 {os.path.join(str(_RESULTS_ROOT), 'question3')} 下）")
    print("  跳过第 6 节的多模型一致性分析；其余各节不受影响。")
else:
    # 计算每对方法之间的相关性
    print(f"\n  各方法日均总预测相关性矩阵:")
    n_methods = len(methods_list)
    for i in range(n_methods):
        row_str = f"  {methods_list[i]:<25}"
        for j in range(n_methods):
            if i == j:
                row_str += f" {'1.000':>8}"
            else:
                vals_i = []
                vals_j = []
                for k in all_keys:
                    if k in method_forecasts[methods_list[i]] and k in method_forecasts[methods_list[j]]:
                        vals_i.extend(method_forecasts[methods_list[i]][k])
                        vals_j.extend(method_forecasts[methods_list[j]][k])
                if len(vals_i) > 0:
                    corr = np.corrcoef(vals_i, vals_j)[0, 1]
                    row_str += f" {corr:>8.4f}"
                else:
                    row_str += f" {'N/A':>8}"
        print(row_str)

    # 每个方法的总预测
    print(f"\n  各方法7天总预测对比:")
    sota_keys = set(method_forecasts[methods_list[0]].keys())
    for method in methods_list:
        total = 0
        for k in sota_keys:
            if k in method_forecasts[method]:
                total += np.sum(method_forecasts[method][k])
        print(f"    {method:<25}: {total:>12.1f} 吨")

# ============================================================
# 7. 不确定集构建改进建议
# ============================================================
print("\n" + "=" * 80)
print("7. 不确定集构建改进建议")
print("=" * 80)

print("""
  7.1 当前方法的局限性
  ─────────────────────────────────────
  (a) CV方法的问题:
      - CV 反映的是历史波动，而非预测误差的波动
      - 对于有趋势的城市-SKU，CV会高估不确定性
      - 对于季节性强的序列，CV可能低估
      - alpha=0.3 是全局缩放，忽略了不同城市-SKU的异质性

  (b) 预测模型本身的不确定性被忽略:
      - 当前delta = CV × y_hat × alpha 仅使用历史波动
      - 未考虑模型本身的预测误差
      - 模型对某些city-SKU可能预测很好(小残差)，对另一些很差

  7.2 改进方案
  ────────────────────────────────────
  方案A: 混合残差-CV方法
    delta = w1 * (CV × y_hat × alpha) + w2 * (std_residual × beta)
    其中w1, w2为可调节权重，beta为置信水平系数
    - 优点: 结合两种方法的优势
    - 可以从回测中直接估计std_residual

  方案B: 分位数回归方法
    - 训练分位数回归模型，直接输出预测区间
    - [Q10, Q90] 作为80%置信区间
    - delta = (Q90 - Q50) 用于上界，delta = (Q50 - Q10) 用于下界
    - 优点: 非参数，自动捕捉异方差性

  方案C: 分组差异化的不确定半径
    - 按CV大小将city-SKU分成3-4组
    - 对每组使用不同的alpha
    - 对高波动组(CV>0.4): alpha=0.5
    - 对低波动组(CV<0.15): alpha=0.2
    - 对中波动组: alpha=0.3
    
  方案D: 基于时间距离的衰减权重
    - 距离预测日越近的残差权重越大
    - delta_t = mean_residual * decay_factor(t)
    - 利用回测中最后3天的残差做加权

  7.3 具体参数建议
  ────────────────────────────────────
""")

# 计算实际建议参数
print(f"  (1) 当前 alpha=0.3 对应的实际覆盖:")
# 以回测残差为基准
resid_to_pred_ratio = np.abs(resid_arr) / (actual_arr + 1e-6)
print(f"      绝对残差/实际值 均值: {np.mean(resid_to_pred_ratio)*100:.1f}%")
print(f"      绝对残差/实际值 中位数: {np.median(resid_to_pred_ratio)*100:.1f}%")

cv_delta_coverage = []
for key in all_keys:
    rd = key_residual_stats[key]
    cv_delta = rd['cv'] * rd['mean_actual'] * alpha
    # 回测7天有多少落在 ±cv_delta 内
    vals = history_dict[key]
    test_vals = vals[train_days:]
    # 模拟预测
    X_train2 = create_simple_features(hist_dates[:train_days])
    X_test2 = create_simple_features(hist_dates[train_days:])
    model2 = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
    model2.fit(X_train2, vals[:train_days])
    preds2 = model2.predict(X_test2)
    inside = np.sum(np.abs(test_vals - preds2) <= cv_delta)
    cv_delta_coverage.append(inside / len(test_vals))

print(f"  CV-based delta 实际覆盖率: {np.mean(cv_delta_coverage)*100:.1f}%")
print(f"  CV-based delta 覆盖率范围: [{np.min(cv_delta_coverage)*100:.1f}%, {np.max(cv_delta_coverage)*100:.1f}%]")

# 推荐alpha
print(f"\n  (2) 建议的分层alpha:")
for label, mask in [('低CV组', low_cv_mask), ('中CV组', mid_cv_mask), ('高CV组', high_cv_mask)]:
    r_std = resid_std_by_key[mask]
    ma = mean_act_by_key[mask]
    cv_g = cv_training[mask]
    # 要达到95%覆盖所需的alpha
    needed_alpha = np.mean(1.96 * r_std / (cv_g * ma + 1e-6))
    print(f"    {label}: 建议 alpha = {min(needed_alpha, 1.0):.3f} (CV均值={np.mean(cv_g):.3f})")

# ============================================================
# 8. 可视化
# ============================================================
print("\n" + "=" * 80)
print("8. 生成可视化图表")
print("=" * 80)

fig, axes = plt.subplots(2, 4, figsize=(20, 11))
fig.suptitle('数据特征深度分析：周期性、趋势性、残差与不确定集', fontsize=16, fontweight='bold')

# (a) 日度总需求时序
ax = axes[0, 0]
days = np.arange(len(hist_dates))
hist_total = np.array(daily_totals_hist['dm']) + np.array(daily_totals_hist['im'])
ax.plot(days, hist_total, 'b-o', 
        markersize=5, label='历史日均总需求', alpha=0.7)
ax.axvline(x=len(hist_dates)-1, color='gray', linestyle='--', alpha=0.5)
# 添加预测期
fc_x = np.arange(len(hist_dates), len(hist_dates) + 7)
fc_total = np.array(daily_totals_fc['dm']) + np.array(daily_totals_fc['im'])
ax.plot(fc_x, fc_total, 'r-s', markersize=5, label='预测日均总需求', alpha=0.7)
ax.set_xlabel('天序号', fontsize=10)
ax.set_ylabel('总需求 (吨)', fontsize=10)
ax.set_title('(a) 日度总需求时序 (历史+预测)', fontsize=11)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# (b) lag-7 自相关分布
ax = axes[0, 1]
ax.hist(lag7_arr, bins=30, edgecolor='black', alpha=0.7, color='steelblue')
ax.axvline(x=0, color='red', linestyle='--', linewidth=1.5, label='零相关')
ax.axvline(x=np.mean(lag7_arr), color='orange', linestyle='-', linewidth=1.5, 
           label=f'均值={np.mean(lag7_arr):.3f}')
ax.set_xlabel('Lag-7 自相关系数', fontsize=10)
ax.set_ylabel('频数', fontsize=10)
ax.set_title('(b) 7天周期自相关分布', fontsize=11)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# (c) 按星期需求分布
ax = axes[0, 2]
x_pos = np.arange(7)
bp = ax.boxplot([weekday_demands[w] for w in range(7)], positions=x_pos, 
                widths=0.5, patch_artist=True)
colors = plt.cm.RdYlGn(np.linspace(0.2, 0.8, 7))
for patch, color in zip(bp['boxes'], colors):
    patch.set_facecolor(color)
ax.set_xticklabels(weekday_names, fontsize=9)
ax.set_ylabel('需求量 (吨)', fontsize=10)
ax.set_title('(c) 按星期需求分布', fontsize=11)
ax.grid(True, alpha=0.3, axis='y')

# (d) 趋势斜率分布
ax = axes[0, 3]
ax.hist(slope_arr, bins=30, edgecolor='black', alpha=0.7, color='forestgreen')
ax.axvline(x=0, color='red', linestyle='--', linewidth=1.5, label='零趋势')
ax.axvline(x=np.mean(slope_arr), color='blue', linestyle='-', linewidth=1.5,
           label=f'均值={np.mean(slope_arr):.3f}')
ax.set_xlabel('趋势斜率 (吨/天)', fontsize=10)
ax.set_ylabel('频数', fontsize=10)
ax.set_title('(d) 线性趋势斜率分布', fontsize=11)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# (e) 残差分布
ax = axes[1, 0]
ax.hist(resid_arr, bins=50, edgecolor='black', alpha=0.7, color='darkorange', density=True)
# 拟合正态
x_fit = np.linspace(np.min(resid_arr), np.max(resid_arr), 200)
norm_fit = stats.norm.pdf(x_fit, np.mean(resid_arr), np.std(resid_arr))
ax.plot(x_fit, norm_fit, 'r-', linewidth=2, label=f'正态拟合 (p={p_norm:.3f})')
ax.set_xlabel('残差 (实际-预测)', fontsize=10)
ax.set_ylabel('密度', fontsize=10)
ax.set_title('(e) 回测残差分布', fontsize=11)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# (f) CV vs 残差std散点
ax = axes[1, 1]
sc = ax.scatter(cv_training, resid_std_by_key, c=mean_act_by_key, 
                cmap='viridis', alpha=0.6, s=30, edgecolors='black', linewidth=0.3)
ax.set_xlabel('训练集CV', fontsize=10)
ax.set_ylabel('回测残差标准差', fontsize=10)
ax.set_title('(f) CV vs 残差标准差', fontsize=11)
plt.colorbar(sc, ax=ax, label='平均需求 (吨)')
ax.grid(True, alpha=0.3)

# (g) 方法间一致性
ax = axes[1, 2]
# 选取两个主要方法
if len(methods_list) >= 2:
    m1, m2 = methods_list[0], methods_list[1]
    vals_m1 = []
    vals_m2 = []
    for k in all_keys:
        if k in method_forecasts[m1] and k in method_forecasts[m2]:
            vals_m1.append(np.sum(method_forecasts[m1][k]))
            vals_m2.append(np.sum(method_forecasts[m2][k]))
    ax.scatter(vals_m1, vals_m2, alpha=0.5, s=20, edgecolors='black', linewidth=0.3)
    ax.plot([min(vals_m1), max(vals_m1)], [min(vals_m1), max(vals_m1)], 
            'r--', linewidth=1.5, label='y=x')
    ax.set_xlabel(f'{m1} 7天总预测', fontsize=9)
    ax.set_ylabel(f'{m2} 7天总预测', fontsize=9)
    ax.set_title('(g) 模型一致性对比', fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

# (h) 不确定半径对比
ax = axes[1, 3]
x_keys = np.arange(min(20, len(all_keys)))
cv_deltas = []
resid_deltas = []
ma_vals = []
for i, key in enumerate(all_keys[:20]):
    rd = key_residual_stats[key]
    cv_deltas.append(rd['cv'] * rd['mean_actual'] * alpha)
    resid_deltas.append(rd['std_residual'] * 1.96)
    ma_vals.append(rd['mean_actual'])

width = 0.35
ax.bar(x_keys - width/2, cv_deltas, width, label='CV方法 (alpha=0.3)', 
       color='steelblue', alpha=0.8)
ax.bar(x_keys + width/2, resid_deltas, width, label='残差方法 (95%CI)', 
       color='darkorange', alpha=0.8)
ax.set_xlabel('城市-SKU序号 (前20)', fontsize=10)
ax.set_ylabel('不确定半径 (吨)', fontsize=10)
ax.set_title('(h) 不确定半径对比 (前20)', fontsize=11)
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3, axis='y')

plt.tight_layout()
fig.savefig(os.path.join(OUTPUT_DIR, 'data_feature_analysis.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  已保存: data_feature_analysis.png")

# 额外：自相关图（选几个代表性城市）
fig2, axes2 = plt.subplots(2, 3, figsize=(18, 10))
fig2.suptitle('代表性城市的自相关图 (ACF)', fontsize=14, fontweight='bold')

# 选择CV低、中、高各2个城市
cv_with_keys = [(cv_full_arr[i], all_keys[i]) for i in range(len(all_keys))]
cv_with_keys.sort()
selected_keys = [
    cv_with_keys[0][1],      # 最低CV
    cv_with_keys[len(cv_with_keys)//4][1],   # 25%分位
    cv_with_keys[len(cv_with_keys)//2][1],   # 中位数
    cv_with_keys[3*len(cv_with_keys)//4][1], # 75%分位
    cv_with_keys[-2][1],     # 次高CV
    cv_with_keys[-1][1],     # 最高CV
]

for idx, key in enumerate(selected_keys):
    r, c = idx // 3, idx % 3
    ax = axes2[r, c]
    vals = history_dict[key]
    acf = compute_acf(vals, max_lag=14)
    lags = np.arange(len(acf))
    ax.stem(lags, acf, linefmt='b-', markerfmt='bo', basefmt='gray')
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    # 95%置信区间
    conf = 1.96 / np.sqrt(len(vals))
    ax.axhline(y=conf, color='red', linestyle='--', alpha=0.7)
    ax.axhline(y=-conf, color='red', linestyle='--', alpha=0.7)
    ax.set_xlabel('滞后天数', fontsize=9)
    ax.set_ylabel('自相关', fontsize=9)
    cv_v = np.std(vals) / np.mean(vals) if np.mean(vals) > 0 else 0
    ax.set_title(f'{key[0]} - {key[1]} (CV={cv_v:.3f})', fontsize=9)
    ax.set_xticks(np.arange(0, 15, 2))
    ax.grid(True, alpha=0.3)

plt.tight_layout()
fig2.savefig(os.path.join(OUTPUT_DIR, 'acf_representative_cities.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  已保存: acf_representative_cities.png")

# 额外：按SKU分别画自相关
fig3, axes3 = plt.subplots(1, 2, figsize=(14, 5))
fig3.suptitle('按SKU分类的Lag-7自相关分布', fontsize=14, fontweight='bold')

for s_idx, sku in enumerate(['dm', 'im']):
    ax = axes3[s_idx]
    sku_lag7 = [lag7_arr[i] for i, k in enumerate(all_keys) if k[1] == sku]
    ax.hist(sku_lag7, bins=20, edgecolor='black', alpha=0.7, 
            color='steelblue' if sku == 'dm' else 'darkorange')
    ax.axvline(x=0, color='red', linestyle='--', linewidth=1.5)
    ax.axvline(x=np.mean(sku_lag7), color='green', linestyle='-', linewidth=1.5,
               label=f'均值={np.mean(sku_lag7):.3f}')
    ax.set_xlabel('Lag-7 自相关系数', fontsize=10)
    ax.set_ylabel('频数', fontsize=10)
    ax.set_title(f'({chr(97+s_idx)}) SKU={sku} (N={len(sku_lag7)})', fontsize=11)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
fig3.savefig(os.path.join(OUTPUT_DIR, 'acf_by_sku.png'), dpi=150, bbox_inches='tight')
plt.close()
print(f"  已保存: acf_by_sku.png")

# ============================================================
# 9. 总结输出
# ============================================================
print("\n" + "=" * 80)
print("9. 分析总结")
print("=" * 80)

peak_day_name = weekday_names[max(peak_counts, key=peak_counts.get)]
peak_count_val = peak_counts[max(peak_counts, key=peak_counts.get)]
pct_positive = np.sum(lag7_arr > 0.1) / len(lag7_arr) * 100
pct_strong = np.sum(lag7_arr > 0.3) / len(lag7_arr) * 100
pct_positive_trend = np.sum(slope_arr > 0) / len(slope_arr) * 100

cycle_conclusion = '存在明显周内周期性' if np.mean(lag7_arr) > 0.1 else '周内周期性较弱'
trend_conclusion = '部分序列存在弱趋势' if trend_significant > 0 else '无明显趋势'
normality_conclusion = '近似正态' if p_norm > 0.05 else '非正态'
ratio_mean_val = np.mean(ratio_arr)
if ratio_mean_val < 0.8:
    cv_vs_resid_conclusion = 'CV方法偏保守'
elif ratio_mean_val < 1.2:
    cv_vs_resid_conclusion = 'CV方法较为合适'
else:
    cv_vs_resid_conclusion = '残差方法更精确'

print("  ┌─────────────────────────────────────────────────────────────────┐")
print("  │                    数据特征分析总结                               │")
print("  ├─────────────────────────────────────────────────────────────────┤")
print("  │                                                                   │")
print("  │  【周期性发现】                                                    │")
print(f"  │  - Lag-7 自相关均值: {np.mean(lag7_arr):.4f}                      │")
print(f"  │  - 强周期 (lag-7 > 0.3) 比例: {pct_strong:.1f}%                  │")
print(f"  │  - 峰值日集中在: {peak_day_name} ({peak_count_val}/{total_keys} 条)│")
print(f"  │  - 结论: {cycle_conclusion} │")
print("  │                                                                   │")
print("  │  【趋势性发现】                                                    │")
print(f"  │  - 显著趋势 (p<0.05) 比例: {trend_significant}/{len(all_keys)} ({trend_significant/len(all_keys)*100:.1f}%)│")
print(f"  │  - 正趋势比例: {pct_positive_trend:.1f}%    │")
print(f"  │  - 结论: {trend_conclusion} │")
print("  │                                                                   │")
print("  │  【残差特征】                                                      │")
print(f"  │  - 残差均值: {np.mean(resid_arr):.4f} (接近0 -> 无偏)               │")
print(f"  │  - 残差标准差: {np.std(resid_arr):.4f}                              │")
print(f"  │  - 正态性 p值: {p_norm:.6f} ({normality_conclusion})│")
print(f"  │  - MAE: {np.mean(abs_resid):.4f}                                   │")
print("  │                                                                   │")
print("  │  【CV vs 残差方法对比】                                            │")
print(f"  │  - CV-based delta (alpha=0.3) 覆盖率: {np.mean(cv_delta_coverage)*100:.1f}%│")
print(f"  │  - 实际平均残差std/需求: {np.mean(resid_std_by_key/(mean_act_by_key+1e-6))*100:.1f}%│")
print(f"  │  - 建议: {cv_vs_resid_conclusion}│")
print("  │                                                                   │")
print("  └─────────────────────────────────────────────────────────────────┘")

# 保存详细结果到CSV
results_df = pd.DataFrame({
    'city': [k[0] for k in all_keys],
    'SKU': [k[1] for k in all_keys],
    'cv_full': cv_full_arr,
    'cv_training': cv_training,
    'lag7_acf': lag7_arr,
    'trend_slope': slope_arr,
    'trend_pvalue': pval_arr,
    'mean_actual': mean_act_by_key,
    'resid_std': resid_std_by_key,
    'resid_mae': resid_mae_arr,
})
results_df.to_csv(os.path.join(OUTPUT_DIR, 'feature_analysis_results.csv'), 
                  index=False, encoding='utf-8-sig')
print(f"  已保存详细结果: feature_analysis_results.csv")

print("\n分析完成。所有图表和结果已保存至:", OUTPUT_DIR)