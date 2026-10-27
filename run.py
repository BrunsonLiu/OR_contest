"""List and launch project tasks without importing solver modules."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import time
import traceback
import uuid

from src.experiment_tracking import capture, experiment_lock, finalize, write_record

ROOT = Path(__file__).resolve().parent
TASKS = {
    "q1": "src/solvers/question1/solve_problem1_cplex.py",
    "q2-time": "src/solvers/question2/solve_problem2_1.py",
    "q2-subsidy": "src/solvers/question2/solve_problem2_2.py",
    "q2-loss": "src/solvers/question2/solve_problem2_3.py",
    "q3": "src/solvers/question3/solve_problem3.py",
    "q3-city": "src/solvers/question3/solve_problem3_comparison.py",
    "q3-methods": "src/solvers/question3/solve_problem3_multimethod.py",
    "q3-backtest": "src/analysis/backtest_forecasts.py",
    "dfl-readiness": "src/analysis/assess_dfl_readiness.py",
    "q4-no-loss": "src/solvers/question4/solve_problem4_no_loss.py",
    "q4-loss": "src/solvers/question4/solve_problem4_loss.py",
    "q4-robust": "src/solvers/question4/solve_problem4_robust.py",
    "analyze-features": "src/analysis/analysis_data_features.py",
    "confirm-instance": "src/analysis/confirm_instance_check.py",
    "confirm-policy": "src/analysis/confirm_policy_compare.py",
    "confirm-scale": "src/analysis/confirm_scale.py",
    "confirm-multi": "src/analysis/confirm_multi.py",
    "confirm-grid": "src/analysis/confirm_grid2d.py",
    "plot-comparison": "src/visualization/visualize_comparison.py",
}


def main():
    parser = argparse.ArgumentParser(description="生鲜仓网优化：统一任务入口")
    parser.add_argument("task", nargs="?", choices=TASKS, help="任务名称")
    parser.add_argument("--list", action="store_true", help="列出任务，不执行求解")
    parser.add_argument("--script", help="运行 src/ 或 archive/ 下的指定 Python 脚本")
    parser.add_argument("--experiment", help="将结果隔离到 results/experiments/名称/")
    parser.add_argument("--purpose", help="本次运行的目的或待验证假设，执行时必填")
    parser.add_argument("--output-dir", type=Path, help="指定独立结果根目录，与 --experiment 二选一")
    parser.add_argument("--forecast-file", type=Path, help="显式指定问题四预测输入")
    parser.add_argument("--loss-version", choices=("legacy", "v2"), help="有损耗绘图输入版本，默认 v2；legacy 仅用于历史对照")
    parser.add_argument("--solver-time-limit", type=float, help="每次 CPLEX 求解的秒数上限")
    parser.add_argument("--solver-threads", type=int, default=2, help="CPLEX 线程数，默认 2")
    parser.add_argument("--solver-gap", type=float, help="CPLEX 相对 gap 上限，0 至 1")
    parser.add_argument("--gamma-values", help="鲁棒模型预算比例列表，如 0,0.025,0.05")
    parser.add_argument("--timeout", type=float, help="整个任务的运行秒数上限")
    args = parser.parse_args()
    if args.task and args.script:
        parser.error("task 与 --script 只能选择一种")
    if args.experiment and args.output_dir:
        parser.error("--experiment 与 --output-dir 只能选择一种")
    if args.experiment and (not args.experiment.replace("-", "").replace("_", "").isalnum()):
        parser.error("实验名称仅允许字母、数字、短横线和下划线")
    if args.solver_threads <= 0 or any(v is not None and (not math.isfinite(v) or v <= 0) for v in (args.solver_time_limit, args.timeout)):
        parser.error("线程数、时间限制必须大于零")
    if args.solver_gap is not None and not 0 <= args.solver_gap <= 1:
        parser.error("--solver-gap 必须介于 0 与 1")
    if args.gamma_values:
        try:
            gammas = [float(value) for value in args.gamma_values.split(",")]
            if not gammas or any(not 0 <= value <= 1 for value in gammas):
                raise ValueError()
        except ValueError:
            parser.error("--gamma-values 必须是介于 0 与 1 的逗号分隔数值")
    if args.list or (not args.task and not args.script):
        for name, path in TASKS.items():
            print(f"{name:20} {path}")
        return
    target = (ROOT / (args.script or TASKS[args.task])).resolve()
    if not any(target.is_relative_to(ROOT / folder) for folder in ("src", "archive")):
        parser.error("脚本必须位于项目的 src/ 或 archive/ 目录内")
    if target.suffix != ".py" or not target.is_file():
        parser.error(f"脚本不存在：{target}")
    if target.name == "visualize_problem1.py":
        parser.error("当前项目只交付 PNG，请使用 visualize_problem1_images.py；不生成 HTML")
    loss_plots = {"vis_daily_cost_loss.py", "visualize_route_onoff_loss.py", "visualize_comparison.py"}
    if args.loss_version and (target.parent != ROOT / "src/visualization" or target.name not in loss_plots):
        parser.error("--loss-version 仅适用于有损耗每日成本、路线开关和成本比较绘图；求解器固定输出 v2")
    if target.is_relative_to(ROOT / "archive"):
        parser.error("历史归档脚本未适配完整记录，请先迁移到 src/ 再运行")
    if not args.purpose or not args.purpose.strip():
        parser.error("执行必须填写 --purpose，说明运行目的或待验证假设")
    if args.forecast_file:
        from src.runtime import read_forecast
        forecast = args.forecast_file.resolve()
        try:
            read_forecast(forecast)
        except (OSError, ValueError) as exc:
            parser.error(f"预测输入无效：{exc}")
    else:
        forecast = ROOT / "results/question3/订单需求量预测结果文件_sota.csv"
    if not args.experiment and not args.output_dir:
        args.experiment = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    result_root = (args.output_dir.resolve() if args.output_dir else ROOT / "results/experiments" / args.experiment)
    if ROOT.is_relative_to(result_root) or result_root == ROOT/"results" or any(result_root.is_relative_to(ROOT / folder) for folder in ("src", "data", "docs", ".git", "archive", "tools", "requirements", "results/question1", "results/question2", "results/question3", "results/question4")):
        parser.error("结果目录不得覆盖源码、原始数据或仓库管理目录")
    task = args.task or target.stem
    try:
        with experiment_lock(result_root):
            return execute_run(args, target, forecast, result_root, task)
    except FileExistsError:
        parser.error("实验目录正在运行或本任务已有记录，请使用新的实验名称；异常中断的锁需核实进程后处理")


def execute_run(args, target, forecast, result_root, task):
    run_folder = result_root / "_runs" / task
    run_folder.mkdir(parents=True)
    env = os.environ.copy()
    for name in ("OR_SOLVER_TIME_LIMIT", "OR_SOLVER_GAP", "OR_GAMMA_VALUES"):
        env.pop(name, None)  # Never inherit undocumented settings from a parent shell.
    env.update(OR_RESULTS_ROOT=str(result_root), OR_FORECAST_FILE=str(forecast),
               OR_LOSS_VERSION=args.loss_version or "v2",
               OR_RUN_DIR=str(run_folder), OR_SOLVER_THREADS=str(args.solver_threads),
               PYTHONPATH=str(ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
               PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", MPLBACKEND="Agg")
    if args.solver_time_limit:
        env["OR_SOLVER_TIME_LIMIT"] = str(args.solver_time_limit)
    if args.solver_gap is not None:
        env["OR_SOLVER_GAP"] = str(args.solver_gap)
    if args.gamma_values:
        env["OR_GAMMA_VALUES"] = args.gamma_values
    manifest = {
        "task": task, "script": target.relative_to(ROOT).as_posix(),
        "script_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_root": str(result_root), "forecast_file": str(forecast),
        "forecast_sha256": hashlib.sha256(forecast.read_bytes()).hexdigest() if forecast.is_file() else None,
        "python": sys.version, "solver_time_limit": args.solver_time_limit,
        "solver_gap": args.solver_gap, "gamma_values": args.gamma_values,
        "loss_version": args.loss_version or "v2",
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in (ROOT / "src").rglob("*.py")},
    }
    manifest.update(capture(ROOT, result_root, run_folder, forecast, args))
    manifest["effective_environment"] = {name: env[name] for name in
        ("OR_SOLVER_TIME_LIMIT", "OR_SOLVER_THREADS", "OR_SOLVER_GAP", "OR_GAMMA_VALUES", "OR_LOSS_VERSION", "PYTHONHASHSEED") if name in env}
    manifest["packages"] = {}
    for package in ("numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "lightgbm", "cplex", "openpyxl", "cartopy", "pyecharts"):
        try:
            manifest["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            manifest["packages"][package] = None
    start = time.monotonic()
    write_record(run_folder/"run.json", manifest)
    print(f"运行 {task}；日志：{run_folder / 'output.log'}", flush=True)
    exit_code = 1
    try:
        with (run_folder / "output.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([sys.executable, "-u", str(target)], cwd=ROOT, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
        exit_code = completed.returncode
        manifest["status"] = "completed" if exit_code == 0 else "failed"
        evidence_file = run_folder / "solver_metrics.jsonl"
        is_solver = target.is_relative_to(ROOT/"src/solvers") and target.parent.name in ("question1", "question2", "question4")
        if exit_code == 0 and is_solver:
            evidence = [json.loads(line) for line in evidence_file.read_text(encoding="utf-8").splitlines()] if evidence_file.exists() else []
            manifest["solver_summary"] = {
                "solves": len(evidence),
                "with_incumbent": sum(bool(item["has_incumbent"]) for item in evidence),
                "optimal_or_within_tolerance": sum(item["status_code"] in (1, 101, 102) for item in evidence),
            }
            if not evidence or not any(item["has_incumbent"] for item in evidence):
                manifest["status"] = "no_feasible_solution"
                exit_code = 2
            elif not all(item["has_incumbent"] for item in evidence):
                manifest["status"] = "completed_with_partial_solutions"
            elif not all(item["status_code"] in (1, 101, 102) for item in evidence):
                manifest["status"] = "completed_with_limits"
    except subprocess.TimeoutExpired:
        manifest["status"] = "timeout"
        exit_code = 124
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        exit_code = 130
    except Exception as exc:
        manifest["status"] = "launcher_failed"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        with (run_folder/"output.log").open("a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
        exit_code = 1
    finally:
        finalize(manifest, result_root, run_folder, ROOT)
        if manifest["changed_source_or_inputs"]:
            manifest["execution_status"] = manifest["status"]
            manifest["status"] = "source_or_inputs_changed"
            exit_code = 3
        manifest.update(exit_code=exit_code, elapsed_seconds=round(time.monotonic()-start, 3))
        write_record(run_folder/"run.json", manifest)
    print(f"{manifest['status']} ({manifest['elapsed_seconds']}s)；结果：{result_root}")
    if exit_code:
        print((run_folder / "output.log").read_text(encoding="utf-8", errors="replace")[-2500:])
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
