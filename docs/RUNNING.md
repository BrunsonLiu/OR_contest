# 运行指南

统一入口会切换到项目根目录，保证历史相对路径按同一基准解析。`--list` 仅列出任务，不会导入求解模块或运行训练。

| 任务 | 命令 | 结果目录 |
| --- | --- | --- |
| 基础仓网优化 | `python run.py q1` | `results/question1/` |
| 时效参数分析 | `python run.py q2-time` | `results/question2/` |
| 开仓补贴方案 | `python run.py q2-subsidy` | `results/question2/` |
| 运输损耗 | `python run.py q2-loss` | `results/question2/` |
| 基线需求预测 | `python run.py q3` | `results/question3/` |
| 城市特征对比 | `python run.py q3-city` | `results/question3/` |
| 多模型预测对比 | `python run.py q3-methods` | `results/question3/` |
| 多日无损耗 | `python run.py q4-no-loss` | `results/question4/problem4_noloss/output_result/` |
| 多日有损耗 | `python run.py q4-loss` | `results/question4/problem4_loss_v2/output_result/` |
| 鲁棒优化 | `python run.py q4-robust` | `results/question4/problem4_robust/` |
| 特征分析 | `python run.py analyze-features` | `results/question3/data_feature_analysis/` |
| 对比绘图 | `python run.py plot-comparison` | `results/question4/problem4_robust/` |

其他绘图或历史脚本也通过同一入口运行，例如：

```powershell
python run.py --script src/visualization/visualize_problem2_loss.py
python run.py --script archive/diagnostics/checks/check_missing.py
```

基础环境：`python -m pip install -r requirements/base.txt`。
地图和交互绘图按需安装：`python -m pip install -r requirements/visualization.txt`。
原项目未提供版本锁，依赖兼容性和 CPLEX 许可仍需在实际运行环境确认。

问题四读取 `results/question3/订单需求量预测结果文件_sota.csv`。基线预测生成 `订单需求量预测结果文件.csv`；两者方法与文件名不同，请确认预测来源后再接入后续优化。部分脚本导入时即开始读数据或求解，不能以直接导入的方式做无副作用检查。
