# 运行指南

所有新求解、训练、回测和绘图通过 `run.py` 启动，必须填写 `--purpose`。完整要求见 [工程标准](ENGINEERING.md)。`python run.py --list` 只列任务，不运行模型。

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements/lock-py312-windows.txt
python tools/check_repository.py
python -m unittest discover -s tests -v
```

版本锁已在 Windows/Python 3.12 验证。完整模型需要超出 CPLEX Community Edition 限制的许可；仅安装依赖不能保证可运行完整模型。PNG 地图需要 `requirements/visualization.txt` 中的可选依赖和底图资源，独立环境地图复现仍待完成。

## 任务与隔离

每次默认创建 `results/experiments/时间-标识/`，也可用 `--experiment 名称` 或 `--output-dir 路径` 指定。以下输出都相对于该实验根目录，不再默认写入历史结果。

| 任务 | 内容 | 输出子目录 |
| --- | --- | --- |
| `q1` | 基础仓网 | `question1/` |
| `q2-time`、`q2-subsidy`、`q2-loss` | 时效、补贴、损耗 | `question2/` |
| `q3`、`q3-city`、`q3-methods` | 预测与方法比较 | `question3/` |
| `q3-backtest` | 滚动回测 | `question3/backtests/` |
| `q4-no-loss` | 多日无损耗 | `question4/problem4_noloss/output_result/` |
| `q4-loss` | 多日有损耗 | `question4/problem4_loss_v2/output_result/` |
| `q4-robust` | 鲁棒优化 | `question4/problem4_robust/` |
| `analyze-features` | 特征分析 | `question3/data_feature_analysis/` |
| `plot-comparison` | 成本与求解质量比较 | `question4/problem4_robust/` |

```powershell
python run.py q1 --experiment baseline-v1 --purpose "验证基础仓网约束与成本分解" --solver-time-limit 60 --timeout 90
python run.py q3 --experiment forecast-v1 --purpose "验证基线时间留出误差并生成未来预测"
python run.py q4-loss --experiment loss-v1 --purpose "验证指定预测输入下的损耗模型" --forecast-file results/experiments/forecast-v1/question3/订单需求量预测结果文件.csv --solver-time-limit 60 --timeout 90
```

问题四未指定 `--forecast-file` 时仍使用历史 SOTA。预测格式检查日期、204 个门店/SKU、唯一性、有限非负需求。选择结果目录不会自动更换预测输入。

同实验同任务拒绝覆盖，同实验禁止并发写入。不同任务仅在输出路径不冲突时共享结果，不同模型方案使用新实验名称。归档脚本不能直接作为新实验运行。源码或原始输入运行中发生变化时，实验标记异常。

## 记录与验收

`_runs/任务/` 保存运行清单、源码/输入快照、完整压缩日志和逐次求解证据。进程启动前记录 running，结束后写终态；失败与超时也保留。

```powershell
python tools/check_experiment.py results/experiments/baseline-v1/_runs/q1/run.json --require-success --report results/experiments/baseline-v1/validation/integrity.json
python tools/audit_results.py results/experiments/baseline-v1 --report results/experiments/baseline-v1/validation/model_checks.json
```

第一条验证证据完整性，第二条独立核算模型结果。完整性不等于数学正确性。旧实验没有 v2 快照和日志时，不能追认为新标准。限时可行解、部分预算点无解和已证明不可行需区分，详看 `solver_metrics.jsonl` 的状态、界与 gap。

## 回测与绘图

```powershell
python run.py q3-backtest --experiment rolling-v1 --purpose "比较固定方法的滚动 RMSE 与排名稳定性" --timeout 900
python tools/verify_backtest_results.py results/experiments/rolling-v1/question3/backtests --report results/experiments/rolling-v1/validation/backtest.json
python run.py --script src/visualization/visualize_problem1_images.py --experiment baseline-v1 --purpose "使用该实验 CSV 生成交付 PNG，核对图表数据源"
```

回测默认最少训练 7 天、步长 3 天、预测 7 天，尾部补齐窗口。窗口重叠，不是独立重复。城市模型按 SKU 跨城市联合训练，未来期无真实值时不宣称实际精度。

只交付必要 PNG，HTML 入口被拒绝。地图可运行 `visualize_problem1_map.py`，超时路线可运行 `visualize_problem1_overtime.py`，同样需要实验目的。

有损耗每日成本图、路线开关图及 `plot-comparison` 默认读取 v2；仅这些图可用 `--loss-version legacy` 显式选择历史数据，不会回退读取其他实验。比较图须具备同实验的确定性和鲁棒输入。

## 专项工具范围

- `tools/audit_question1_workbooks.py`：只读历史 Excel 和固定实验，检查字段、数量和地图证据，不改写工作簿；见 [说明](audits/2026-10-15/QUESTION1_FIELDS_AND_MAPS.md)。
- `tools/audit_timeliness_semantics.py`：固定历史 SOTA，比较末段与 CDC 起算累计时间；自定义预测暂不在该工具范围。
- `tools/verify_small_robust_model.py`：真实 CPLEX 小模型核查，可用于 Community Edition，完整模型另需许可。

专项检查输出保存在对应实验的 `validation/`，与检查命令及输入一起保留。它们不作为科学实验替代统一入口。
