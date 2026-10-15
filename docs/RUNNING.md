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
Windows / Python 3.12 复现实验可安装 `requirements/lock-py312-windows.txt`。独立环境安装和测试已验证；完整模型需要超出 CPLEX Community Edition 限制的许可。

问题四读取 `results/question3/订单需求量预测结果文件_sota.csv`。基线预测生成 `订单需求量预测结果文件.csv`；两者方法与文件名不同，请确认预测来源后再接入后续优化。部分脚本导入时即开始读数据或求解，不能以直接导入的方式做无副作用检查。

## 隔离实验与预测输入

建议为每组实验指定名称，避免修改历史基线：

```powershell
python run.py q3 --experiment my-run
python run.py q4-loss --experiment my-run --forecast-file results/experiments/my-run/question3/订单需求量预测结果文件.csv --solver-time-limit 60 --timeout 180
python run.py --script src/visualization/visualize_problem1_images.py --experiment my-run
```

默认仍使用历史 SOTA 输入；指定结果目录不会自动替换预测输入。`--forecast-file` 会校验日期、门店/SKU、重复键及非负有限数值。

同一实验中不同任务可以共享结果；同一任务已存在运行记录时会拒绝覆盖。重复实验请换名称。也可用 `--output-dir` 指定结果根目录，该参数与 `--experiment` 互斥。原始归档脚本未统一支持隔离运行，不能为其指定实验目录。

每个任务在结果根目录下 `_runs/任务名/` 保存 `run.json`、本地 `output.log`，求解任务还保存 `solver_metrics.jsonl`。后续运行清单记录源码与预测文件指纹及依赖版本。日志受 `.gitignore` 排除，机器可读记录及结果可提交。扫描任务运行完成不代表每个参数组合有可行解；需要查看逐次求解状态和 gap。

## 验证与历史追溯

问题一历史 Excel 与当前 CSV 的字段、数量口径及地图坐标核查可运行 `python tools/audit_question1_workbooks.py`，需要 openpyxl。该工具只读 Excel，不导出或改写工作簿；其固定审计对象及绘图验收条件见 [说明](audits/2026-10-15/QUESTION1_FIELDS_AND_MAPS.md)。

```powershell
python tools/check_repository.py
python -m unittest discover -s tests -v
python tools/check_environment.py --solver-smoke --report results/environment.json
python tools/audit_results.py results/experiments/audit-fixed-20261015 --report results/checks.json
python tools/verify_legacy_forecast.py --output-dir results/experiments/legacy-check
```

修正后的预测统一使用时间留出验证；不会用未来预测与不同日期的历史真实值比较。每种方法另存验证预测和 `metrics_*.json`，生产预测与验证预测分别训练。城市特征对比改为按 SKU 跨城市联合训练，不再沿用旧单序列实验中的“静态特征改善精度”解释。

## 鲁棒预算与求解精度

`--gamma-values 0,0.025,0.05` 可选择要扫描的预算比例，`--solver-gap 0.001` 可覆盖相对 gap 目标。预算比例乘以每天所有门店/SKU 的条目数得到共享预算，并不是需求吨数的上浮百分比。当前集合仅允许需求向上波动。小模型集成检查可用 `python tools/verify_small_robust_model.py --report results/robust-small.json`，在新安装的 Community Edition 环境中已验证通过。

## 配送策略独立核算

有损耗求解器固定输出 `problem4_loss_v2`。每日成本图、路线开关图和 `plot-comparison` 默认读取 v2，可加 `--loss-version legacy` 显式读取所选实验中的旧目录，不自动回退。历史版本缺少生成参数记录，详见 [版本核查](audits/2026-10-15/LOSS_VERSIONS.md)。

滚动回测：`python run.py q3-backtest --experiment my-backtest --timeout 900`。默认最少训练 7 天、步长 3 天、预测 7 天，末尾补齐最后窗口；重叠窗口不是独立重复。

```powershell
python tools/verify_backtest_results.py results/experiments/my-backtest/question3/backtests --report results/backtest-check.json
python tools/audit_timeliness_semantics.py results/experiments/robust-discount-20261015/question4/problem4_robust/robust_results.json --report results/time-check.json
```

时效工具固定使用历史 SOTA 输入，比较末段与 CDC 起算的累计运输时间，不修改求解模型。自定义预测输入暂不在该工具核查范围。

新鲁棒结果保存 `assignment_policy`、`smart_warehouses` 和 `policy_worst_case_cost`。审计工具根据各任务 `run.json` 定位并核对预测输入指纹，从原始数据独立重算偏差半径、真实净单价，以及容量、时效和成本的最坏情景 LP。若原路径在另一台电脑不存在，可用 `--forecast-file` 指定指纹一致的预测文件。旧结果没有逐路线策略时，只能执行其具备证据的成本分解检查，不会标记为策略核查已完成。
