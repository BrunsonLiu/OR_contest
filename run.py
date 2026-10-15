"""List and launch project tasks without importing solver modules."""
from pathlib import Path
import argparse
import os
import runpy
import sys

ROOT = Path(__file__).resolve().parent
TASKS = {
    "q1": "src/solvers/question1/solve_problem1_cplex.py",
    "q2-time": "src/solvers/question2/solve_problem2_1.py",
    "q2-subsidy": "src/solvers/question2/solve_problem2_2.py",
    "q2-loss": "src/solvers/question2/solve_problem2_3.py",
    "q3": "src/solvers/question3/solve_problem3.py",
    "q3-city": "src/solvers/question3/solve_problem3_comparison.py",
    "q3-methods": "src/solvers/question3/solve_problem3_multimethod.py",
    "q4-no-loss": "src/solvers/question4/solve_problem4_no_loss.py",
    "q4-loss": "src/solvers/question4/solve_problem4_loss.py",
    "q4-robust": "src/solvers/question4/solve_problem4_robust.py",
    "analyze-features": "src/analysis/analysis_data_features.py",
    "plot-comparison": "src/visualization/visualize_comparison.py",
}


def main():
    parser = argparse.ArgumentParser(description="生鲜仓网优化：统一任务入口")
    parser.add_argument("task", nargs="?", choices=TASKS, help="任务名称")
    parser.add_argument("--list", action="store_true", help="列出任务，不执行求解")
    parser.add_argument("--script", help="运行 src/ 或 archive/ 下的指定 Python 脚本")
    args = parser.parse_args()
    if args.task and args.script:
        parser.error("task 与 --script 只能选择一种")
    if args.list or (not args.task and not args.script):
        for name, path in TASKS.items():
            print(f"{name:20} {path}")
        return
    target = (ROOT / (args.script or TASKS[args.task])).resolve()
    if not any(target.is_relative_to(ROOT / folder) for folder in ("src", "archive")):
        parser.error("脚本必须位于项目的 src/ 或 archive/ 目录内")
    if target.suffix != ".py" or not target.is_file():
        parser.error(f"脚本不存在：{target}")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(target.parent))
    sys.argv = [str(target)]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
