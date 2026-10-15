# 结果导航

数据文件和既有结果按内容校验，搬动前后完全一致。新运行的输出按题号归档。

| 目录 | 内容 |
| --- | --- |
| `question1/` | 基础仓网结果及图片 |
| `question2/` | 时效、补贴和损耗分析 |
| `question3/` | 预测、模型比较与特征分析 |
| `question4/problem4_noloss/` | 多日无损耗实验 |
| `question4/problem4_loss/` | 历史有损耗实验，部分历史绘图使用 |
| `question4/problem4_loss_v2/` | 当前有损耗入口输出 |
| `question4/problem4_robust/` | 鲁棒优化、JSON 结果和图表 |

## 新审计实验

- `experiments/audit-20261015/`：本轮成本修正前的运行证据，预测评估已使用新流程。
- `experiments/audit-fixed-20261015/`：修正后的四题运行结果、验证误差、旧预测重建及逐次求解状态。
- `experiments/audit-cleanenv-20261015/`：独立环境完整问题一的许可限制复现记录。
- 原目录下的历史结果没有被覆盖，不代表已按修正模型通过验证。

- `experiments/robust-ratio-20261015/`：第二轮时效比例与 CDC 容量修正后的预算扫描，包含真实状态和 gap。

## 已保存文件

### question1

- [Q1-result1.xlsx](question1/Q1-result1.xlsx)
- [Q1-result2.xlsx](question1/Q1-result2.xlsx)
- [Q1-result3.xlsx](question1/Q1-result3.xlsx)
- [Q3-result.xlsx](question1/Q3-result.xlsx)
- [问题1_仓库分布_地图.png](question1/问题1_仓库分布_地图.png)
- [问题1_所有备选仓库位置.png](question1/问题1_所有备选仓库位置.png)
- [问题1_综合报告_地图.png](question1/问题1_综合报告_地图.png)
- [问题1_运输网络_地图.png](question1/问题1_运输网络_地图.png)
- [问题1_运输网络_超时路径.png](question1/问题1_运输网络_超时路径.png)

### question2

- [仓→仓损耗明细文件_完整版_cplex.csv](question2/仓→仓损耗明细文件_完整版_cplex.csv)
- [仓→店损耗明细文件_完整版_cplex.csv](question2/仓→店损耗明细文件_完整版_cplex.csv)
- [仓库处置订单量文件_有补贴_cplex.csv](question2/仓库处置订单量文件_有补贴_cplex.csv)
- [仓库处置订单量文件_运输损耗_cplex.csv](question2/仓库处置订单量文件_运输损耗_cplex.csv)
- [仓网业务表现文件_运输损耗_cplex.csv](question2/仓网业务表现文件_运输损耗_cplex.csv)
- [仓网供应关系文件_有补贴_cplex.csv](question2/仓网供应关系文件_有补贴_cplex.csv)
- [仓网供应关系文件_运输损耗_cplex.csv](question2/仓网供应关系文件_运输损耗_cplex.csv)
- [开仓补贴政策对比_cplex.csv](question2/开仓补贴政策对比_cplex.csv)
- [时效与成本关系分析.csv](question2/时效与成本关系分析.csv)
- [时效与成本关系分析_摘要.csv](question2/时效与成本关系分析_摘要.csv)
- [问题2_损耗成本最高的15条路径.png](question2/问题2_损耗成本最高的15条路径.png)
- [问题2_时效与成本关系分析.png](question2/问题2_时效与成本关系分析.png)
- [问题2_运输网络_损耗成本.png](question2/问题2_运输网络_损耗成本.png)

### question3

- [city_feature_comparison.png](question3/city_feature_comparison.png)
- [data_feature_analysis/acf_by_sku.png](question3/data_feature_analysis/acf_by_sku.png)
- [data_feature_analysis/acf_representative_cities.png](question3/data_feature_analysis/acf_representative_cities.png)
- [data_feature_analysis/data_feature_analysis.png](question3/data_feature_analysis/data_feature_analysis.png)
- [data_feature_analysis/feature_analysis_results.csv](question3/data_feature_analysis/feature_analysis_results.csv)
- [multimethod_comparison.png](question3/multimethod_comparison.png)
- [SOTA_Forecast_Examples.png](question3/SOTA_Forecast_Examples.png)
- [历史订单趋势.png](question3/历史订单趋势.png)
- [多方法对比报告.md](question3/多方法对比报告.md)
- [实验对比报告_城市特征影响.md](question3/实验对比报告_城市特征影响.md)
- [订单需求量预测结果_实验一_纯时间序列.csv](question3/订单需求量预测结果_实验一_纯时间序列.csv)
- [订单需求量预测结果_实验二_加入城市特征.csv](question3/订单需求量预测结果_实验二_加入城市特征.csv)
- [订单需求量预测结果文件_sota.csv](question3/订单需求量预测结果文件_sota.csv)
- [超参数选择与多方法对比分析.md](question3/超参数选择与多方法对比分析.md)
- [预测结果_GradientBoosting.csv](question3/预测结果_GradientBoosting.csv)
- [预测结果_LightGBM.csv](question3/预测结果_LightGBM.csv)
- [预测结果_MLP.csv](question3/预测结果_MLP.csv)
- [预测结果_RandomForest.csv](question3/预测结果_RandomForest.csv)
- [预测结果_SVR.csv](question3/预测结果_SVR.csv)

### question4

- [problem4_loss/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_loss/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_loss/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_loss/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_loss/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_loss/output_result/仓网业务表现文件_汇总.csv](question4/problem4_loss/output_result/仓网业务表现文件_汇总.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_loss/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_loss/output_result/仓网供应关系文件_2016-06-30.csv)
- [problem4_loss/output_result/动态路线优化可视化_问题4_有损耗.png](question4/problem4_loss/output_result/动态路线优化可视化_问题4_有损耗.png)
- [problem4_loss/output_result/每日成本变化_有损耗.png](question4/problem4_loss/output_result/每日成本变化_有损耗.png)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv](question4/problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_loss_v2/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_loss_v2/output_result/仓网供应关系文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓库处置订单量文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓库处置订单量文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓网业务表现文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓网业务表现文件_2016-06-30.csv)
- [problem4_noloss/output_result/仓网业务表现文件_汇总.csv](question4/problem4_noloss/output_result/仓网业务表现文件_汇总.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-24.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-24.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-25.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-25.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-26.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-26.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-27.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-27.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-28.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-28.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-29.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-29.csv)
- [problem4_noloss/output_result/仓网供应关系文件_2016-06-30.csv](question4/problem4_noloss/output_result/仓网供应关系文件_2016-06-30.csv)
- [problem4_robust/first_principles_analysis.png](question4/problem4_robust/first_principles_analysis.png)
- [problem4_robust/price_of_robustness.png](question4/problem4_robust/price_of_robustness.png)
- [problem4_robust/robust_results.json](question4/problem4_robust/robust_results.json)
- [problem4_robust/warehouse_comparison_map.png](question4/problem4_robust/warehouse_comparison_map.png)
- [problem4_robust/仓网业务表现文件_汇总.csv](question4/problem4_robust/仓网业务表现文件_汇总.csv)

