"""Enumerate Wayback Machine copies of the DOHMH restaurant inspection dataset.

Queries the CDX API for every URL variant under the Socrata dataset 43nn-pn8j
(rows.csv/json/xml/tsv, geospatial exports, resource/ and odata endpoints),
keeps status-200 captures that are large enough to be full exports, and picks
one capture per snapshot window (preferring CSV over JSON over XML).

Usage: python pipeline/dohmh_wayback.py  -> writes data/raw/dohmh/wayback_candidates.csv
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

CDX = "https://web.archive.org/cdx/search/cdx"
PREFIXES = [
    "data.cityofnewyork.us/api/views/43nn-pn8j/",
    "data.cityofnewyork.us/api/geospatial/43nn-pn8j",
    "data.cityofnewyork.us/resource/43nn-pn8j",
    "data.cityofnewyork.us/api/odata/v4/43nn-pn8j",
    "data.cityofnewyork.us/download/43nn-pn8j",
    "data.cityofnewyork.us/api/views/xx67-kt59/",
    "data.cityofnewyork.us/resource/xx67-kt59",
    "nycopendata.socrata.com/api/views/43nn-pn8j",
    "nycopendata.socrata.com/api/views/xx67-kt59",
]
# Wayback 'length' is the compressed WARC record size; full exports are >= several MB.
MIN_LEN = 3_000_000
FORMAT_PREF = {"csv": 0, "json": 1, "xml": 2}
DEDUPE_DAYS = 14  # captures this close together add almost nothing to churn coverage

OUT = Path(__file__).resolve().parent.parent / "data/raw/dohmh/wayback_candidates.csv"


def cdx(prefix: str) -> list[list[str]]:
    params = {"url": prefix, "matchType": "prefix", "output": "json",
              "fl": "timestamp,original,statuscode,mimetype,length,digest",
              "collapse": "digest", "filter": "statuscode:200", "limit": "10000"}
    for attempt in range(6):
        try:
            r = requests.get(CDX, params=params, timeout=180)
            r.raise_for_status()
            rows = r.json()
            return rows[1:] if rows else []
        except (requests.RequestException, ValueError) as e:
            wait = 10 * (attempt + 1)
            print(f"CDX {prefix} failed ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"CDX query failed repeatedly for {prefix}")


def fmt_of(url: str, mime: str) -> str | None:
    u = url.lower()
    if "rows.csv" in u or "format=csv" in u:
        return "csv"
    if "rows.json" in u:
        return "json"
    if "rows.xml" in u:
        return "xml"
    return None  # tsv/pdf/kml/shapefile/geojson exports duplicate same-day CSV captures


def main() -> None:
    caps = []
    for p in PREFIXES:
        for ts, orig, st, mime, length, digest in cdx(p):
            f = fmt_of(orig, mime)
            if f and length.isdigit() and int(length) >= MIN_LEN:
                caps.append({"timestamp": ts, "url": orig, "format": f,
                             "cdx_length": int(length), "digest": digest})
        time.sleep(3)
    caps.sort(key=lambda c: (c["timestamp"], FORMAT_PREF[c["format"]]))
    chosen: list[dict] = []
    for c in caps:
        d = datetime.strptime(c["timestamp"][:8], "%Y%m%d")
        if chosen:
            last = chosen[-1]
            ld = datetime.strptime(last["timestamp"][:8], "%Y%m%d")
            if (d - ld).days < DEDUPE_DAYS:
                # keep the better format, else the earlier one
                if FORMAT_PREF[c["format"]] < FORMAT_PREF[last["format"]]:
                    chosen[-1] = c
                continue
        chosen.append(c)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(chosen[0].keys()))
        w.writeheader()
        w.writerows(chosen)
    print(f"{len(caps)} large captures -> {len(chosen)} chosen; wrote {OUT}")


if __name__ == "__main__":
    main()
