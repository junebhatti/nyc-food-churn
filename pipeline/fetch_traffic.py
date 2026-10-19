"""Reproduce every foot-traffic dataset in data/raw/traffic/ (notes: data/notes/traffic.md).

    .venv/bin/python pipeline/fetch_traffic.py              # everything (~4-6 h, mostly Socrata)
    .venv/bin/python pipeline/fetch_traffic.py tlc build    # just some steps

Steps: lodes, acs, ped (DOT counts), subway (hourly + MetroCard + turnstile samples; slow),
tlc (all TLC months via remote duckdb), citibike (May+Oct samples), bid (BID counts),
build (tract x year panel + composite index + lot helper; needs the others).
Monthly Socrata/TLC results are cached in data/raw/traffic/_tmp/ so reruns resume.
Needs: duckdb, geopandas, scipy, pyproj, openpyxl, xlrd in .venv.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import traffic_acs  # noqa: E402
import traffic_bid  # noqa: E402
import traffic_build  # noqa: E402
import traffic_citibike  # noqa: E402
import traffic_lodes  # noqa: E402
import traffic_ped  # noqa: E402
import traffic_subway  # noqa: E402
import traffic_tlc  # noqa: E402

STEPS = {"lodes": traffic_lodes.run, "acs": traffic_acs.run, "ped": traffic_ped.run,
         "subway": traffic_subway.run, "tlc": traffic_tlc.run, "citibike": traffic_citibike.run,
         "bid": traffic_bid.run, "build": traffic_build.run}

if __name__ == "__main__":
    steps = sys.argv[1:] or list(STEPS)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        sys.exit(f"unknown step(s) {unknown}; choose from {list(STEPS)}")
    for s in steps:
        STEPS[s]()
