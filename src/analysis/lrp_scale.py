"""Run the same LRP comparison at twenty stores and capacity four."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import src.analysis.lrp_localsearch as base

base.N_STORES = 20
base.CAPACITY = 4

if __name__ == "__main__":
    base.main()
