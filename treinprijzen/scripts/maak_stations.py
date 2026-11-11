"""Maakt data/stations.json uit de open stationslijst van Trainline (ODbL).

    git clone --depth 1 https://github.com/trainline-eu/stations /tmp/tl
    python3 scripts/maak_stations.py /tmp/tl/stations.csv > data/stations.json

Per station (EVA-nummer of UIC-code) de NS International-code (Benerail) en het land.\nHet land van andere stations volgt uit het EVA-nummer (84 = NL, 88 = BE, 80 = DE, 82 = LU).
"""
import csv
import json
import sys

LANDEN = {"NL", "BE", "LU", "DE"}
uit = {}
with open(sys.argv[1], encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if r["country"] not in LANDEN or not r["db_id"]:
            continue
        eva = r["db_id"]
        item = {"naam": r["name"], "land": r["country"]}
        if not r["benerail_id"] or r["benerail_is_enabled"] != "t":
            continue
        item["nsi"] = r["benerail_id"]
        # Op EVA-nummer (DB) én UIC-code: bij Belgische stations verschillen die soms.
        # Bij dubbele nummers wint het hoofdstation.
        for sleutel in {eva, r["uic"]} - {""}:
            if sleutel not in uit or r["is_main_station"] == "t":
                uit[sleutel] = item
json.dump(dict(sorted(uit.items())), sys.stdout, ensure_ascii=False, separators=(",", ":"))
