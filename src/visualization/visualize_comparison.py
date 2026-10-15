"""Plot measured incumbent costs, without using unselected candidate routes."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))
import json
import math
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from src.runtime import results_root


def main():
    root = results_root()
    output = root / "question4/problem4_robust"
    source = root / "question4/problem4_loss_v2/output_result/仓网业务表现文件_汇总.csv"
    deterministic = pd.read_csv(source).iloc[0]
    robust = json.loads((output / "robust_results.json").read_text(encoding="utf-8"))
    feasible = [row for row in robust if row.get("total_cost") is not None and math.isfinite(row["total_cost"])]
    nominal = next((row for row in feasible if row["gamma"] == 0), None)
    if nominal is None:
        raise ValueError("缺少 Gamma=0 可行解，不能进行名义成本比较")
    columns = ["仓库到门店的运输总成本（万元）", "仓库之间的运输总成本（万元）", "处置总成本（万元）", "损耗总成本（万元）", "开仓总成本（万元）", "智能系统采购总成本（万元）"]
    robust_columns = ["transport_cost_customer", "transport_cost_warehouse", "proc_cost_actual", "loss_cost", "open_cost", "smart_cost"]
    labels = ["Delivery", "Transfer", "Handling", "Loss", "Opening", "Smart systems"]
    values = np.array([[float(deterministic[key]) for key in columns], [nominal[key] for key in robust_columns]])
    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(2)
    for index, label in enumerate(labels):
        ax.bar([0, 1], values[:, index], bottom=bottom, label=label)
        bottom += values[:, index]
    ax.set_xticks([0, 1], ["Deterministic incumbent", "Robust Gamma=0 incumbent"])
    ax.set_ylabel("Cost (10,000 CNY)")
    ax.set_title("Exported cost components (incumbents, not exact optima)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "comparison_costs.png", dpi=150)
    plt.close(fig)

    evidence_path = root / "_runs/q4-robust/solver_metrics.jsonl"
    evidence = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()] if evidence_path.exists() else []
    quality = {row["gamma"]: evidence[i] for i, row in enumerate(robust)} if len(evidence) == len(robust) else {}
    fig, ax = plt.subplots(figsize=(10, 6))
    for row in feasible:
        record = quality.get(row["gamma"], row)
        limited = record.get("status_code") not in (1, 101, 102)
        color = "tab:orange" if limited else "tab:blue"
        x, y = row["gamma"] * 100, row["total_cost"]
        ax.scatter(x, y, color=color, marker="x" if limited else "o")
        bound = record.get("best_bound")
        if bound is not None and math.isfinite(bound) and 0 <= bound <= y:
            ax.vlines(x, bound, y, color=color)
        gap = record.get("relative_gap")
        text = f"gap={gap:.1%}" if gap is not None else "gap unavailable"
        ax.annotate(text, (x, y), xytext=(4, 5), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Uncertainty budget (%)")
    ax.set_ylabel("Incumbent cost (10,000 CNY)")
    ax.set_title("Feasible incumbents and bounds; orange = no optimality certificate")
    fig.tight_layout()
    fig.savefig(output / "robust_incumbents.png", dpi=150)
    plt.close(fig)
    report = {
        "deterministic_source": str(source), "robust_gamma": 0,
        "deterministic_components": dict(zip(labels, values[0].tolist())),
        "robust_components": dict(zip(labels, values[1].tolist())),
        "caveats": ["Components come from exported solutions, not sums over all candidate routes.", "Formulation equivalence requires separate review.", "Incumbents are not exact optimal costs."],
    }
    (output / "comparison_sources.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved measured comparison plots to {output}")


if __name__ == "__main__":
    main()
