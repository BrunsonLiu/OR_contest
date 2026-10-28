"""Run the live-seafood recovery comparison at six batches."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import src.analysis.live_scale as base

base.N = 6
base.PERIODS = 6
base.DEADLINE_HIGH = 5
base.SEEDS = 10

if __name__ == "__main__":
    base.main()
