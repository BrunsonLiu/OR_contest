"""Illustrative real-network instance for the MLOR problem.

Uses three contest RDCs, twelve nearby contest cities, the contest last-leg
transport rate, and transparent age/MLOR assumptions. It is an illustration on
real geography, not a field study: demands are unit, ages and MLOR are assigned
by rule, and the costs are the contest rates.
"""
from pathlib import Path as _RepoPath
_REPO_ROOT = next(p for p in _RepoPath(__file__).resolve().parents if (p / "run.py").is_file())
import sys
sys.path.insert(0, str(_REPO_ROOT))

import csv
import importlib
import json
import math

import src.analysis.mlor_scale as base
from src.runtime import ROOT, results_root

RDC_NAMES = ["guang-zhou-DC", "dong-guan-DC", "cheng-du-DC"]
N_STORES = 12


def load_locations():
    locations = {}
    with (ROOT / "data/raw/df_loc.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            population = float(row["resident_pop"]) if row["resident_pop"].strip() else 0.0
            locations[row["Location"]] = (float(row["Longitude"]), float(row["Latitude"]), population)
    with (ROOT / "data/raw/df_wh.csv").open(encoding="utf-8-sig", newline="") as source:
        warehouse_locations = {row["Name"]: row["Location"] for row in csv.DictReader(source)
                               if row["Name"] in RDC_NAMES}
    return locations, warehouse_locations


def haversine(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def build():
    locations, warehouse_locations = load_locations()
    warehouses = []
    for index, name in enumerate(RDC_NAMES):
        city = warehouse_locations[name]
        lon, lat, _ = locations[city]
        warehouses.append({"name": name, "lon": lon, "lat": lat, "age": [0.0, 2.5, 4.5][index]})
    candidates = [name for name in locations if name not in set(warehouse_locations.values())]
    scored = sorted(candidates, key=lambda name: min(
        haversine(locations[name][:2], (warehouse["lon"], warehouse["lat"])) for warehouse in warehouses))
    chosen = scored[:N_STORES]
    lon0 = sum(locations[name][0] for name in chosen) / len(chosen)
    lat0 = sum(locations[name][1] for name in chosen) / len(chosen)
    for warehouse in warehouses:
        warehouse["x"] = (warehouse["lon"] - lon0) * 111.0 * math.cos(math.radians(lat0))
        warehouse["y"] = (warehouse["lat"] - lat0) * 111.0
        warehouse["point"] = (warehouse["x"], warehouse["y"])
    populations = sorted((locations[name][2] for name in chosen), reverse=True)
    threshold_high = populations[len(populations) // 3]
    threshold_low = populations[2 * len(populations) // 3]
    stores = []
    for name in chosen:
        lon, lat, population = locations[name]
        mlor = 3.0 if population >= threshold_high else (2.0 if population >= threshold_low else 1.0)
        stores.append({
            "name": name,
            "x": (lon - lon0) * 111.0 * math.cos(math.radians(lat0)),
            "y": (lat - lat0) * 111.0,
            "mlor": mlor,
            "population": population,
        })
    return warehouses, stores


def unserved_list(stores, routes):
    served = {store for route_list in routes.values() for order in route_list for store in order}
    return [store for store in range(len(stores)) if store not in served]


def main():
    warehouses, stores = build()
    base.WAREHOUSES = warehouses
    base.COST_PER_KM = 1.45
    base.KM_PER_DAY = 100.0
    base.SHELF_LIFE = 6.0
    base.OPEN_COST = 100.0
    base.VEHICLE_COST = 50.0
    base.PENALTY = 200.0

    import src.analysis.mlor_alns as alnsmod
    importlib.reload(alnsmod)

    aware_routes = alnsmod.construct(stores, "actual", True)[1]
    aware_unserved = unserved_list(stores, aware_routes)
    aware_actual = alnsmod.solution_cost(aware_routes, aware_unserved, stores)
    blind_routes = alnsmod.construct(stores, "zero", False)[1]
    blind_unserved = unserved_list(stores, blind_routes)
    blind_actual = alnsmod.solution_cost(blind_routes, blind_unserved, stores)
    best, _ = alnsmod.alns(stores, iterations=200, seed=0)

    summary = {
        "instance": "three contest RDCs, twelve nearest cities, contest last-leg rate",
        "warehouses": [{"name": w["name"], "age": w["age"], "x": round(w["x"], 1), "y": round(w["y"], 1)}
                       for w in warehouses],
        "stores": [{"name": s["name"], "mlor": s["mlor"], "population": s["population"]} for s in stores],
        "greedy_aware": aware_actual,
        "greedy_blind": blind_actual,
        "alns_aware": best,
        "alns_improvement": aware_actual - best,
        "scope": "real geography, unit demand, rule-based ages and MLOR; illustrative only",
        "limitations": [
            "Unit demand ignores the contest demand weights.",
            "Ages and MLOR are assigned by rule, not observed.",
            "This is an illustration, not a case study or a field estimate.",
        ],
    }
    out_dir = results_root() / "mlor_case"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
                                          encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("greedy_aware", "greedy_blind", "alns_aware", "alns_improvement")}, ensure_ascii=False))
    print("Outputs:", out_dir)


if __name__ == "__main__":
    main()
