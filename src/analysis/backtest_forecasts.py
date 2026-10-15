"""Run the fixed expanding-window forecast comparison."""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))
from src.backtesting import run_backtest

if __name__ == "__main__":
    run_backtest()
