"""Wall-clock runtime of the exact DP and the four heuristics.

Times are single-process, single-threaded measurements on the same machine.
They include the algorithm's own evaluation and repair work, not file IO.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import json
import platform
import time

import src.analysis.mlor_alns as alnsmod
from src.analysis.mlor_alns import alns
from src.analysis.mlor_ga import genetic
from src.analysis.mlor_sa import sa
from src.analysis.mlor_scale import make_instance
from src.analysis.mlor_tabu import tabu_search
from src.runtime import results_root

SEEDS = [0, 1, 2]
SIZES = [8, 12, 20]


def timed_alns(stores, seed):
    calls = [0]
    original = alnsmod.solution_cost

    def counted(routes, unserved, stores_arg=None):
        calls[0] += 1
        return original(routes, unserved, stores_arg)

    alnsmod.solution_cost = counted
    start = time.perf_counter()
    alns(stores, iterations=200, seed=seed, destroy_min=4, destroy_max=6)
    elapsed = time.perf_counter() - start
    alnsmod.solution_cost = original
    return elapsed, calls[0]


def main():
    import src.analysis.mlor_dp2 as dp8
    rows = []
    for seed in SEEDS:
        start = time.perf_counter()
        dp8.main(seeds=[seed], label="runtime eight", write=False)
        rows.append({"size": 8, "seed": seed, "method": "DP", "seconds": time.perf_counter() - start})
    import src.analysis.mlor_dp12 as dp12
    for seed in SEEDS:
        start = time.perf_counter()
        dp12.dp.main(seeds=[seed], label="runtime twelve", write=False)
        rows.append({"size": 12, "seed": seed, "method": "DP", "seconds": time.perf_counter() - start})

    for size in SIZES:
        for seed in SEEDS:
            stores = make_instance(seed, size)
            elapsed, evaluations = timed_alns(stores, seed)
            rows.append({"size": size, "seed": seed, "method": "ALNS", "seconds": elapsed,
                         "evaluations": evaluations})
            start = time.perf_counter()
            sa(stores, evaluations, seed)
            rows.append({"size": size, "seed": seed, "method": "SA", "seconds": time.perf_counter() - start})
            start = time.perf_counter()
            tabu_search(stores, evaluations, seed)
            rows.append({"size": size, "seed": seed, "method": "Tabu", "seconds": time.perf_counter() - start})
            start = time.perf_counter()
            genetic(stores, evaluations, seed)
            rows.append({"size": size, "seed": seed, "method": "GA", "seconds": time.perf_counter() - start})

    means = {}
    for size in SIZES:
        means[str(size)] = {}
        for method in ["DP", "ALNS", "SA", "Tabu", "GA"]:
            values = [row["seconds"] for row in rows if row["size"] == size and row["method"] == method]
            if values:
                means[str(size)][method] = sum(values) / len(values)
    summary = {
        "seeds": SEEDS,
        "sizes": SIZES,
        "machine": platform.processor() or platform.platform(),
        "platform": platform.platform(),
        "rows": rows,
        "means": means,
        "scope": "single-process wall-clock; same machine; ALNS 200 iterations, alternatives same evaluation budget",
        "limitations": ["Times depend on the Python implementation and machine.",
                        "No compiler-level optimization or parallelization."],
    }
    out_dir = results_root() / "mlor_runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({"means": means, "machine": summary["machine"]}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
