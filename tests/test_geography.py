import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.geography import warehouse_coordinates
from src.runtime import ROOT


class GeographyTests(unittest.TestCase):
    def test_every_actual_warehouse_is_mapped_to_its_source_location(self):
        with (ROOT/"data/raw/df_wh.csv").open(encoding="utf-8-sig") as source:
            facilities = list(csv.DictReader(source))
        with (ROOT/"data/raw/df_loc.csv").open(encoding="utf-8-sig") as source:
            locations = {row["Location"]: [float(row["Longitude"]), float(row["Latitude"])] for row in csv.DictReader(source)}
        coordinates = warehouse_coordinates()
        expected = {row["Name"] for row in facilities if row["Type"] in ("CDC", "RDC")}
        self.assertEqual(set(coordinates), expected)
        for row in facilities:
            if row["Name"] in expected:
                self.assertEqual(coordinates[row["Name"]], locations[row["Location"]])

    def test_missing_and_duplicate_coordinates_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root/"data/raw"
            raw.mkdir(parents=True)
            (raw/"df_wh.csv").write_text("Name,Type,Location\nw,CDC,missing\n", encoding="utf-8")
            with patch("src.geography.ROOT", root):
                for contents in ("Location,Longitude,Latitude\nother,1,2\n",
                                 "Location,Longitude,Latitude\nmissing,1,2\nmissing,3,4\n",
                                 "Location,Longitude,Latitude\nmissing,nan,2\n"):
                    (raw/"df_loc.csv").write_text(contents, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        warehouse_coordinates()
