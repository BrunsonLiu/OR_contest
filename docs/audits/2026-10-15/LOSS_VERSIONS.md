# 第五轮：有损耗结果版本与绘图一致性

## 默认版本与历史证据

当前唯一有损耗确定性求解入口为 `q4-loss`，输出 `question4/problem4_loss_v2/output_result/`。`problem4_loss` 是保留的历史版本，不是第二个可选求解器。

两个历史目录各有 22 份 CSV，文件集合和字段一致，但没有一份文件内容完全相同。汇总成本分别为 233185.84、233949.68 万元，智能系统成本分别为 27、25.5 万元。二者没有足够运行记录，因此不能把差异归因于某个参数、某项模型改动，也不能声称能够精确复现旧版本。

机器可读清单、字段、逐文件 SHA256 和汇总见 [loss_versions.json](loss_versions.json)，可运行 `python tools/audit_loss_versions.py` 重建。`legacy` 与 `historical_v2` 两份清单的 SHA256 按 CRLF 工作区字节计算，与 `data/raw/**`、`results/questionN/**/*.csv` 一同受 `.gitattributes` 的 `eol=crlf` 保护；`corrected_v2` 位于 `results/experiments/**`（逐字节保护）。三条记录均已用上述工具刷新，逐文件哈希与当前文件一致；`tools/check_line_endings.py` 复核 `legacy` 与 `historical_v2`（`results/questionN/**` 受 `eol=crlf` 保护），experiments 项不在其断言面内，清单缺失或为空即失败。

当前源代码可以确认的参数：损耗在 500 分钟后按 `0.2*(分钟-500)^2/10000` 万元/吨计算；时效门槛为末段 600 分钟，名义需求量加权达标比例 95%；处理费计一次，智能系统优惠为处理费的 40%；默认 gap 0.005、时限 1800 秒，允许统一入口覆盖。这里描述当前源码，不追认两个历史目录的生成参数。

有运行记录的修正实验位于 `results/experiments/audit-fixed-20261015/`，有损耗汇总成本为 233162.81 万元、处理费 666.25 万元。本轮没有重新求解或改写历史 CSV，也不将新旧成本差简单当成模型修正的净收益。

## 修复的混用和图表问题

- 两张有损耗图原先固定读取旧目录，与求解器及成本比较图不同；现在三者统一默认 v2。
- 新增 `--loss-version legacy|v2`，只允许用于有损耗每日成本、路线开关与成本比较图。求解器不接受这个参数，避免误认为能生成旧模型；每次运行清单记录版本。结果根目录仍受实验目录控制。
- 每日“需求”原先把 CDC→RDC 中转量和仓库→门店需求一起相加；现在仅计服务对象为原始门店的货量。
- 路线图原先写死“67 条动态、201 条静态”，现在根据实际策略计数。修正实验实际为 70 条动态、199 条静态路线。缺失每日文件会报错，不再被当作当天无路线；无动态路线可以正常绘图。
- 求解器说明不再承诺全局最优，修正了与实际代码不符的默认时限和 gap 描述。

## 验证与限制

25 项自动测试、仓库结构检查通过。在独立环境中用修正实验实际执行两张图，均完成；已检查输出图片。该环境没有 Cartopy，路线开关热图可用，地理地图显示缺少依赖的说明，不能算地图部分验收完成。问题一历史 Excel 字段映射及其余地图验证继续保留待办。

运行方式：

```powershell
python run.py q4-loss --experiment new-loss --solver-time-limit 60
python run.py --script src/visualization/vis_daily_cost_loss.py --experiment new-loss
python run.py --script src/visualization/visualize_route_onoff_loss.py --experiment new-loss
python run.py plot-comparison --experiment new-loss --loss-version v2
```

成本比较还需要同一实验中的鲁棒结果；不能只生成确定性结果便运行比较。历史对照可指定 `--loss-version legacy`，需在选定结果根目录提供对应历史文件，不会回退混用其他实验。不要向原历史目录写新图；可先将待比较数据复制到独立实验目录。
