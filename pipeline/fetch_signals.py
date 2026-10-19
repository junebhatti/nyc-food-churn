"""Fetch dated proof-of-life / open-close signals for NYC food & drink businesses.

    .venv/bin/python pipeline/fetch_signals.py              # every source
    .venv/bin/python pipeline/fetch_signals.py 311 ppp      # just these
    .venv/bin/python pipeline/signals_eval.py               # usefulness vs DOHMH / SLA

Outputs: data/raw/signals/<name>.parquet + manifest.json. See data/notes/signals.md.
All pulls are SoQL-filtered Socrata queries, sequential, with gov_common.get's retry/backoff.
"""
from __future__ import annotations

import sys
import time

import signals_city as city
import signals_state as state

SOURCES = {
    "311": city.fetch_311,
    "dob_bis": city.fetch_dob_bis,
    "dob_now": city.fetch_dob_now,
    "open_rest_insp": city.fetch_open_rest_insp,
    "nycba": city.fetch_nycba,
    "ppp": state.fetch_ppp,
    "rrf": state.fetch_rrf,
    "dos": state.fetch_dos,  # after ppp/rrf: matches their borrower names too
}


def main(names: list[str]) -> None:
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        sys.exit(f"unknown source(s) {unknown}; choose from {list(SOURCES)}")
    for n in names or list(SOURCES):
        t = time.time()
        print(f"== {n}", flush=True)
        SOURCES[n]()
        print(f"   {n} done in {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
