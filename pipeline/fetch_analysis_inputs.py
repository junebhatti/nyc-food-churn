"""Build data/raw/analysis_inputs/ (variables for analyses A-E). See data/notes/analysis_inputs.md.

Usage: .venv/bin/python pipeline/fetch_analysis_inputs.py [step ...]
Steps (default: all, in this order):
  base cuisine chains operators dos operators2 storefront size rent age rrf register coverage
Network: cuisine (GitHub, once), chains (Wikipedia API, once; cached in _src/), dos (data.ny.gov,
~45 requests). The rent PDFs/CSVs in rent/ were fetched once (REBNY, nyc.gov, 2 via Wayback) and are
re-parsed by ai_rent_rebny_bk.py / ai_rent_dof_rpie.py (see their docstrings).
Inputs from other areas are read-only; rerun after dohmh/extra changes the union.
"""
from __future__ import annotations

import sys

import pandas as pd

import ai_age
import ai_base
import ai_chains
import ai_coverage
import ai_cuisine
import ai_dos_process
import ai_operators
import ai_rent
import ai_rrf
import ai_size
import ai_storefront
from ai_common import OUT, write_out


def register():
    """Add the once-fetched rent / RRF reference files to manifest.json (no rewrite of the data)."""
    import json
    from datetime import datetime, timezone
    from ai_common import MANIFEST
    m = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    files = {
        "rent/outer_borough_corridor_rents": ("rent/outer_borough_corridor_rents.csv",
                                              "REBNY Brooklyn Retail Reports 3Q2015-H1 2025 (rebny.com PDFs)",
                                              "ground-floor asking $/sqft/yr by corridor; parsed by ai_rent_rebny_bk.py"),
        "rent/dof_rpie_retail_income_by_borough": ("rent/dof_rpie_retail_income_by_borough.csv",
                                                   "NYC DOF Additional Statistical Distributions FY2015-FY2027",
                                                   "RPIE gross income $/sqft, retail buildings, by borough, filing years "
                                                   "2012-2024; FY2016 typed from image; FY2017-18 PDFs via Wayback"),
    }
    for k, (f, src, note) in files.items():
        p = OUT / f
        d = pd.read_csv(p)
        m[k] = {"file": f, "rows": int(len(d)), "columns": list(d.columns), "source": src, "notes": note,
                "built": datetime.now(timezone.utc).isoformat(timespec="seconds"), "bytes": p.stat().st_size}
    for p in sorted((OUT / "rent" / "pdf").glob("*.pdf")) + sorted((OUT / "rrf").glob("*.pdf")):
        rel = str(p.relative_to(OUT))
        m[rel] = {"file": rel, "bytes": p.stat().st_size, "source": "public PDF", "notes": "reference document"}
    MANIFEST.write_text(json.dumps(m, indent=1, sort_keys=True))


STEPS = {
    "base": ai_base.build, "cuisine": ai_cuisine.build, "chains": ai_chains.build,
    "operators": ai_operators.build, "dos": ai_dos_process.build, "operators2": ai_operators.build,
    "storefront": ai_storefront.build, "size": ai_size.build, "rent": ai_rent.build, "age": ai_age.build,
    "rrf": ai_rrf.build, "register": register, "coverage": ai_coverage.build,
}

if __name__ == "__main__":
    for s in sys.argv[1:] or list(STEPS):
        if s not in STEPS:
            raise SystemExit(f"unknown step {s}; choose from {list(STEPS)}")
        print(f"== {s}", flush=True)
        STEPS[s]()
