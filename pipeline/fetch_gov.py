"""Reproduce every government / licensing / storefront / rent / geography dataset in data/raw/gov/.

    .venv/bin/python pipeline/fetch_gov.py            # everything (~20-30 min)
    .venv/bin/python pipeline/fetch_gov.py sla geo    # just some steps

Steps: sla (NYSLA current + Wayback), city (storefronts, outdoor dining, DCWP), dof (assessed
market values), geo (boundaries + slim PLUTO), geocode (PAD/SND index; 'geocode_eval' re-runs the
GeoSearch comparison), rebny (Manhattan corridor asking rents from PDFs; needs pdftotext).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import gov_city  # noqa: E402
import gov_dof  # noqa: E402
import gov_geo  # noqa: E402
import gov_geocode  # noqa: E402
import gov_rebny  # noqa: E402
import gov_sla  # noqa: E402

STEPS = {
    "sla": gov_sla.run, "city": gov_city.run, "dof": gov_dof.run, "geo": gov_geo.run,
    "geocode": gov_geocode.build, "rebny": gov_rebny.run, "geocode_eval": gov_geocode.evaluate,
}
DEFAULT = ["sla", "city", "dof", "geo", "geocode", "rebny"]  # geo before geocode (needs PLUTO)

if __name__ == "__main__":
    steps = sys.argv[1:] or DEFAULT
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        sys.exit(f"unknown step(s) {unknown}; choose from {list(STEPS)}")
    for s in steps:
        STEPS[s]()
