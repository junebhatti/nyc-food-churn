"""Research datasets with dated per-venue activity in NYC (check-ins, reviews).

Run: .venv/bin/python pipeline/fetch_research_poi.py [gl2018 tsmc msteps lbsn match]
  (no args = all, ~45 min; lbsn streams ~2.2 GB and gl2018 ~1.8 GB over HTTP,
   nothing global is written to disk)
Outputs in data/raw/research_poi/; notes in data/notes/research_poi.md.
"""
from __future__ import annotations

import sys

import rpoi_foursquare
import rpoi_googlelocal2018
import rpoi_match

STEPS = {
    "gl2018": rpoi_googlelocal2018.run,
    "tsmc": rpoi_foursquare.run_tsmc,
    "msteps": rpoi_foursquare.run_msteps,
    "lbsn": rpoi_foursquare.run_lbsn,
    "match": rpoi_match.run,
}

if __name__ == "__main__":
    for step in sys.argv[1:] or list(STEPS):
        if step not in STEPS:
            sys.exit(f"unknown step {step!r}; choose from {list(STEPS)}")
        print(f"== {step} ==")
        STEPS[step]()
