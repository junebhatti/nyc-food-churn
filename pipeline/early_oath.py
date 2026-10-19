"""Fetch OATH Health Tribunal cases issued by DOHMH food safety (BFSCS), 1990s..2014.

Source: NYC Open Data jz4z-kudi "OATH Hearings Division Case Status". Each DOHMH
restaurant-inspection Notice of Violation that went to the tribunal is one row,
with violation_date = inspection date, respondent (legal entity) name, premises
borough, respondent house number and zip, and up to 10 DOHMH violation codes.
This is the only dated, citywide restaurant-level record we have before 2012-07.

Output: data/raw/early/oath_bfscs.csv.gz (raw API fields, one row per ticket).
Run:    .venv/bin/python pipeline/early_oath.py
"""
from __future__ import annotations

import csv
import gzip
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/raw/early/oath_bfscs.csv.gz"
API = "https://data.cityofnewyork.us/resource/jz4z-kudi.json"
WHERE = "issuing_agency='DOHMH - BFSCS' AND violation_date < '2015-01-01'"
FIELDS = (["ticket_number", "violation_date", "violation_time", "issuing_agency", "respondent_last_name",
           "violation_location_borough", "violation_location_city", "violation_location_zip_code",
           "respondent_address_borough", "respondent_address_house", "respondent_address_zip_code",
           "hearing_status", "hearing_result", "hearing_date", "decision_date", "penalty_imposed",
           "total_violation_amount"]
          + [f"charge_{i}_code" for i in range(1, 11)])
PAGE = 50000


def page(offset: int) -> list[dict]:
    params = {"$select": ",".join(FIELDS), "$where": WHERE, "$order": "ticket_number",
              "$limit": PAGE, "$offset": offset}
    for attempt in range(5):
        try:
            r = requests.get(API, params=params, timeout=(30, 300))
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                raise ValueError(f"unexpected response: {str(rows)[:200]}")
            return rows
        except (requests.RequestException, ValueError) as e:
            print(f"  offset {offset} attempt {attempt + 1}: {e}", file=sys.stderr)
            if attempt == 4:
                raise
            time.sleep(15 * (attempt + 1))
    raise AssertionError("unreachable")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    n = 0
    with gzip.open(tmp, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        while True:
            rows = page(n)
            for r in rows:
                unknown = set(r) - set(FIELDS)
                if unknown:
                    raise ValueError(f"unexpected fields {unknown}")
                w.writerow(r)
            n += len(rows)
            print(f"  {n:,} rows", file=sys.stderr)
            if len(rows) < PAGE:
                break
            time.sleep(2)
    tmp.rename(OUT)
    print(f"wrote {OUT} ({n:,} rows, {OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
