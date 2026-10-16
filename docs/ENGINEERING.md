# 工程与实验标准

本标准适用于后续实验。统一入口负责记录与隔离，任务专属检查负责验证数值和科学结论。已有旧实验不补造记录。

## 启动与隔离

以下 `--experiment` 名称是示意值，并非仓库中已存在的实验；实际运行请换成本次自己的名称（省略该参数则由入口自动生成）。

```powershell
python run.py q3-backtest --experiment weekly-baseline-v1 --purpose "比较固定方法在滚动窗口的 RMSE，检查排名稳定性" --timeout 900
```

执行必须填写目的。不提供实验名称时自动使用 UTC 时间与随机标识创建新目录，不再默认写历史 `results/questionN`。同一实验的同一任务拒绝重复运行；目录锁阻止同一实验内并发写入。异常强制结束可能留下锁和 running 记录，必须先确认原进程结束，再处理锁并使用新实验名，不能直接重跑覆盖证据。

同组不同任务可共享数据，但必须使用不冲突的输出文件；不同模型方案用不同实验名称。记录会列出新增、修改、删除的产物；已有 CSV/JSON 在快照中保留运行前版本。改变配置重跑时使用新名称。绘图只生成必要 PNG，HTML 入口被统一入口拒绝。归档脚本必须先迁移才可接入新实验。

## 每次运行的证据

| 文件或字段 | 内容 |
| --- | --- |
| `run.json` | schema 版本、目的、原始命令、解析参数、起止时间、状态、退出码、耗时 |
| `git` | Git 提交、分支、工作区状态；有改动时不能仅用提交号识别实际源码 |
| `environment` | Python 路径、操作系统、全部已安装包的版本；不采集口令或整个环境变量集合 |
| `effective_environment` | 入口明确设置的求解控制值、哈希种子等；清除父进程残留的时限、gap、预算设置 |
| `snapshot.zip` | 当时的 `run.py`、`src` 源码、原始输入、依赖声明、预测输入、该实验已有 CSV/JSON 输入副本 |
| `snapshot.members` | 每个快照成员及整个压缩包的 SHA256 |
| `output.log.gz` | 完整标准输出与错误日志，压缩后可随必要结果提交；本地原始 `.log` 仍忽略 |
| `solver_metrics.jsonl` | 每次真实求解的状态、是否有解、目标值、界、gap，以及实际时限、线程和种子等参数 |
| `artifacts` | 本次新增/修改产物的相对路径与 SHA256；快照、日志、求解证据单独校验 |

运行前先原子写入 running 记录，结束后更新终态。进程失败、超时、手动中断均保留记录；运行中源码、原始输入或预测文件变化，实验不再标为成功。突发断电或强制终止可能只留下 running，校验工具会拒绝认定其完整。

实验目录由 `.gitattributes` 禁用换行自动转换，确保 Git 提交、拉取后的记录和产物仍保留原始字节指纹。旧实验不批量改写；v2 工程验收记录已按此方式保存。

换行策略按“是否会被指纹断言”分为两类，仓库规范形态统一为 LF 索引：

- **受指纹断言保护的输入**（`data/raw/**` 与 `results/question1|2|3|4/**/*.csv`）固定为 `text eol=crlf`。历史记录中的 `forecast_sha256`、`history_sha256`、`tools/audit_results.py` 的预测校验与 `tools/audit_loss_versions.py` 的损耗版本清单都按 CRLF 工作区字节计算，`eol=crlf` 让 Linux、macOS 与 CI 检出也得到同一份 CRLF 字节，不再依赖本机 `core.autocrlf`。
- **源码**（`run.py`、`src/**`、`requirements/**`）为 `text`，仓库内保持 LF；其历史工作区哈希（`source_sha256`、`script_sha256`）仅在 Windows 构建机以 CRLF 生成，`experiment_tracking.finalize` 只把它们当信息记录、不作断言，因此源码仍随检出设置变化。

`tools/check_line_endings.py` 断言这些属性规则生效、索引为 LF、工作区为 CRLF，并复核已提交回测、运行记录和损耗版本清单里的输入指纹。已提交回测缺少 `history_sha256`、或运行清单引用了受指纹保护的预测却缺少 `forecast_sha256`，都判为错误而非跳过，避免缺失指纹被当作通过。`check_experiment_bytes` 另行断言 `results/experiments/**` 仍由 `-text` 逐字节保护——该目录不是换行转换面，若其规则被改成 `text` 或缺失即失败。缺规则或指纹不符即失败，CI 在 `check_repository.py` 之后运行该检查。

快照是运行时文件证据，不保证跨操作系统、不同求解许可或底层计算库得到逐位相同结果；复现实验仍需匹配环境、许可和业务定义。代码内模型超参数由源码快照追溯，CPLEX 参数另由实际求解记录确认。外部输入未接入快照前不得据其开展正式新实验。

## 两层验收

```powershell
python tools/check_experiment.py results/experiments/weekly-baseline-v1/_runs/q3-backtest/run.json --require-success --report results/experiments/weekly-baseline-v1/validation/integrity.json
python tools/verify_backtest_results.py results/experiments/weekly-baseline-v1/question3/backtests --expected-methods SeasonalNaive,LastValue,pooled_time,pooled_city,RandomForest,GradientBoosting,SVR,MLP,LightGBM --report results/experiments/weekly-baseline-v1/backtest-check.json
```

第一条校验快照、日志、产物和求解证据是否完整、是否发生改动。`--require-success` 只接受 completed；限时可行解或部分解可以做完整性检查，但不能冒充完整成功。第二条独立重算回测误差，属于专属数值验证。求解任务使用成本、容量和时效的独立审计，不能用文件指纹证明数学正确或最优。

人工或专属验证生成的检查文件也应保留在对应实验中。若运行后修改已登记的输出，旧记录校验应失败；重新生成须新建实验，或作为有记录的新任务，并明确其对旧证据的影响。

正式引用需要：完整记录通过、专属验证通过、说明业务假设与数据范围、披露实际 gap/失败状态。历史文件来源不明、未来真值缺失、样本太短等问题不能用工程记录消除。

## 提交前检查

每次提交前运行：

```powershell
python tools/check_repository.py
python tools/check_line_endings.py
python -m unittest discover -s tests -v
```

当前测试为 8 个文件、54 项（以 `python -m unittest discover -s tests -v` 实际输出为准）；`docs/audits/` 中出现的旧测试项数是当时的点状快照，不代表当前数量。
