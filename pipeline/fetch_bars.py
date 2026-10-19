"""Pre-2015 bar / liquor-licence evidence for NYC. See data/notes/bars.md.

Usage: .venv/bin/python pipeline/fetch_bars.py [cabaret] [cb] [build]
  cabaret  DCWP cabaret licences from the gov pull (no network)
  cb       community-board SLA items from Wayback copies of CB PDFs (archive.org, slow: ~1.5 h first run;
           cached text in data/raw/bars/_cache/cb_txt is reused)
  build    normalize the 2016-02 SLA snapshot and count pre-2015 evidence per lot
"""
from __future__ import annotations

import sys

import bars_build
import bars_cabaret
import bars_cb

STEPS = {"cabaret": bars_cabaret.run, "cb": bars_cb.run, "build": bars_build.run}

if __name__ == "__main__":
    for step in sys.argv[1:] or list(STEPS):
        if step not in STEPS:
            sys.exit(f"unknown step {step!r}; choose from {list(STEPS)}")
        print(f"== {step}", flush=True)
        STEPS[step]()
