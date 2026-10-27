"""Minimal assortment-network check: does confirmation cost change the design?

Two candidate warehouses serve one store with eight SKUs. Each warehouse may
carry b SKUs; an unserved SKU triggers a customer confirmation with cost c.
Holding is convex in breadth. The model is deliberately small and linear /
quadratic so the switch point can be checked by hand.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import json

from src.runtime import results_root

SKUS = 8
WAREHOUSES = {
    "near": {"fixed": 10.0, "transport_per_sku": 1.0, "holding": 0.5},
    "far": {"fixed": 4.0, "transport_per_sku": 2.0, "holding": 0.25},
}


def cost(name, breadth, confirmation_cost):
    data = WAREHOUSES[name]
    return (data["fixed"] + data["transport_per_sku"] * SKUS
            + data["holding"] * breadth ** 2
            + confirmation_cost * (SKUS - breadth))


def best_design(confirmation_cost):
    options = []
    for name in WAREHOUSES:
        for breadth in range(SKUS + 1):
            options.append((cost(name, breadth, confirmation_cost), name, breadth))
    value, name, breadth = min(options)
    return {"confirmation_cost": confirmation_cost, "warehouse": name,
            "breadth": breadth, "cost": value}


def main():
    rows = [best_design(c) for c in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0)]
    out_dir = results_root() / "assortment_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "designs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["confirmation_cost", "warehouse", "breadth", "cost"])
        writer.writeheader()
        writer.writerows(rows)
    switches = [{"from": rows[index]["warehouse"], "to": rows[index + 1]["warehouse"],
                 "between": [rows[index]["confirmation_cost"], rows[index + 1]["confirmation_cost"]]}
                for index in range(len(rows) - 1) if rows[index]["warehouse"] != rows[index + 1]["warehouse"]]
    summary = {
        "skus": SKUS, "warehouses": WAREHOUSES, "rows": len(rows),
        "design_switch": bool(switches), "switches": switches,
        "baseline_without_confirmation": rows[0],
        "high_confirmation": rows[-1],
        "scope": "one store, two warehouses, eight SKUs; convex holding; confirmation cost per unserved SKU",
        "limitations": [
            "The stockout-to-confirmation mapping is linear and stylised; no real store data.",
            "The direction of the switch depends on the chosen holding/transport parameters.",
            "This tests a mechanism, not the presence of the gap in the literature.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({"design_switch": summary["design_switch"], "switches": switches}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
