"""Reproduce the non-government POI pulls into data/raw/poi/.

Usage:
  .venv/bin/python pipeline/fetch_poi.py [fsq] [overture] [osm] [ohsome] [combine]
  (no args = all). Optional: --only <release> (repeatable) for fsq/overture.

Sources and caveats are documented in data/notes/poi.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

STEPS = ["fsq", "overture", "osm", "ohsome", "combine"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="*", choices=STEPS + [[]], default=[])
    ap.add_argument("--only", action="append", default=None)
    a = ap.parse_args()
    steps = a.steps or STEPS
    only = set(a.only) if a.only else None
    if "fsq" in steps:
        import poi_fsq
        poi_fsq.run(only)
    if "overture" in steps:
        import poi_overture
        poi_overture.run(only)
    if "osm" in steps:
        import poi_osm
        poi_osm.run()
    if "ohsome" in steps:
        import poi_ohsome
        poi_ohsome.run()
    if "combine" in steps:
        import poi_combine
        poi_combine.run()


if __name__ == "__main__":
    main()
