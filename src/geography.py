"""Resolve warehouse coordinates from the authoritative facility/location tables."""
import csv
import math

from src.runtime import ROOT


def warehouse_coordinates():
    with (ROOT/"data/raw/df_loc.csv").open(encoding="utf-8-sig", newline="") as source:
        locations = {}
        for row in csv.DictReader(source):
            name = row["Location"]
            if name in locations:
                raise ValueError(f"城市坐标键重复: {name}")
            coordinates = [float(row["Longitude"]), float(row["Latitude"])]
            if not all(math.isfinite(value) for value in coordinates) or not (-180 <= coordinates[0] <= 180 and -90 <= coordinates[1] <= 90):
                raise ValueError(f"城市坐标无效: {name}")
            locations[name] = coordinates
    with (ROOT/"data/raw/df_wh.csv").open(encoding="utf-8-sig", newline="") as source:
        warehouses = {}
        for row in csv.DictReader(source):
            if row["Type"] not in ("CDC", "RDC"):
                continue
            if row["Name"] in warehouses:
                raise ValueError(f"仓库名称重复: {row['Name']}")
            if row["Location"] not in locations:
                raise ValueError(f"仓库缺少城市坐标: {row['Name']}")
            warehouses[row["Name"]] = locations[row["Location"]].copy()
    return warehouses
