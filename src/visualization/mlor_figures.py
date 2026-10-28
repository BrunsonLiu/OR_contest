"""Figures for the MLOR paper draft: penalty sensitivity and ALNS ablation."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src.runtime import results_root  # noqa: E402

SENSITIVITY = _REPO_ROOT / "results/experiments/mlor-sensitivity-20261028/mlor_sensitivity/summary.json"
ABLATION = _REPO_ROOT / "results/experiments/mlor-ablation-20261028b/mlor_ablation/summary.json"


def plot_sensitivity(out_dir):
    data = json.loads(SENSITIVITY.read_text(encoding="utf-8"))["penalties"]
    penalties = sorted(float(key) for key in data)
    lookup = {float(key): value["mean_gap"] for key, value in data.items()}
    gaps = [lookup[penalty] for penalty in penalties]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(penalties, gaps, marker="o", color="#1f4e79", linewidth=1.8)
    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Penalty per infeasible delivery")
    ax.set_ylabel("Mean gap: age-blind − age-aware")
    ax.set_title("Penalty sensitivity (8 stores, exact DP)")
    gap0 = lookup[0.0]
    gap50 = lookup[50.0]
    break_even = 50.0 * (-gap0) / (gap50 - gap0)
    ax.annotate(f"break-even ≈ {break_even:.1f}", xy=(break_even, 0), xytext=(break_even + 60, -0.35),
                arrowprops={"arrowstyle": "->", "color": "black"}, fontsize=8)
    fig.tight_layout()
    path = out_dir / "penalty_sensitivity.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_ablation(out_dir):
    data = json.loads(ABLATION.read_text(encoding="utf-8"))["variants"]
    labels = ["Greedy", "No unserved retry", "Full ALNS"]
    keys = ["greedy", "no_retry", "full"]
    values = [data[key]["mean_gap"] for key in keys]
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(labels, values, color=["#a6a6a6", "#7f9fb5", "#1f4e79"])
    ax.set_ylabel("Mean gap to exact")
    ax.set_title("ALNS ablation (12 stores)")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 8, f"{value:.1f}",
                ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, max(values) * 1.15)
    fig.tight_layout()
    path = out_dir / "alns_ablation.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def main():
    out_dir = results_root() / "mlor_figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    first = plot_sensitivity(out_dir)
    second = plot_ablation(out_dir)
    print("Figures:", first, second)


if __name__ == "__main__":
    main()
