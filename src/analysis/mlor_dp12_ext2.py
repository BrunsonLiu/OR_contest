"""Exact 12-store DP for hold-out seeds 15-19."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import importlib

import src.analysis.mlor_scale as base

base.N_STORES = 12

import src.analysis.mlor_dp2 as dp

importlib.reload(dp)

if __name__ == "__main__":
    dp.main(seeds=range(15, 20), label="twelve stores")
