"""Profile every downloaded DOHMH copy, fill the manifest stats columns, build
the union inspection table and print coverage.

Outputs:
  data/raw/dohmh/manifest.csv            (stats columns updated in place)
  data/raw/dohmh/union_inspections.parquet  one row per (camis, inspection_date)
      across all copies (old WebExtract copies lack inspection_type), attributes from the latest copy that
      has the inspection, plus first/last snapshot_date that contained it.
  data/raw/dohmh/coverage_by_year.csv
Run: .venv/bin/python pipeline/dohmh_profile.py
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/dohmh"
MANIFEST = RAW / "manifest.csv"

# canonical name -> accepted normalized source column names
SYN = {
    "camis": ["camis"],
    "dba": ["dba"],
    "boro": ["boro", "borough"],
    "building": ["building"],
    "street": ["street"],
    "zipcode": ["zipcode", "zip"],
    "phone": ["phone"],
    "cuisine": ["cuisine_description", "cuisinecode", "cuisine_code"],
    "inspection_date": ["inspection_date", "inspdate"],
    "action": ["action"],
    "violation_code": ["violation_code", "violcode"],
    "score": ["score"],
    "grade": ["grade", "currentgrade"],
    "record_date": ["record_date", "recorddate"],
    "inspection_type": ["inspection_type"],
    "latitude": ["latitude", "location_latitude"],
    "longitude": ["longitude", "location_longitude"],
    "bbl": ["bbl"],
    "bin": ["bin"],
}


def norm(c: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", c.strip().lstrip("﻿").lower()).strip("_")


def date_expr(col: str) -> str:
    c = f"trim({col})"
    return f"""coalesce(
      try_strptime({c}, '%m/%d/%Y')::date,
      try_strptime(left({c}, 10), '%Y-%m-%d')::date,
      try_strptime({c}, '%m/%d/%Y %I:%M:%S %p')::date,
      try_strptime({c}, '%m/%d/%y')::date,
      CASE WHEN regexp_full_match({c}, '[0-9]{{5}}(\\.0+)?')
           THEN DATE '1899-12-30' + CAST(CAST({c} AS DOUBLE) AS INTEGER) END)"""


def load(con: duckdb.DuckDBPyConnection, path: Path, view: str) -> list[str]:
    opts = "all_varchar=true, header=true, sample_size=-1, strict_mode=false"
    try:
        con.execute(f"CREATE OR REPLACE TABLE raw_{view} AS SELECT * FROM read_csv('{path}', {opts})")
    except duckdb.NotImplementedException as e:
        # quoted fields with embedded newlines defeat the parallel reader
        print(f"  {path.name}: {str(e)[:80]}; retrying single-threaded", file=sys.stderr)
        con.execute(f"CREATE OR REPLACE TABLE raw_{view} AS SELECT * FROM "
                    f"read_csv('{path}', {opts}, parallel=false)")
    cols = [r[0] for r in con.execute(f"DESCRIBE raw_{view}").fetchall()]
    by_norm = {norm(c): c for c in cols}
    sel = []
    for canon, alts in SYN.items():
        src = next((by_norm[a] for a in alts if a in by_norm), None)
        sel.append(f'"{src}" AS {canon}' if src else f"NULL::VARCHAR AS {canon}")
    con.execute(f"""CREATE OR REPLACE TABLE t_{view} AS
        SELECT * REPLACE ({date_expr('inspection_date')} AS inspection_date,
                          {date_expr('record_date')} AS record_date)
        FROM (SELECT {', '.join(sel)} FROM raw_{view})""")
    con.execute(f"DROP TABLE raw_{view}")
    return [norm(c) for c in cols]


def main() -> None:
    with MANIFEST.open() as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())
    con = duckdb.connect()
    parts = []
    for r in rows:
        f = RAW / f"{r['id']}.csv.gz"
        if not f.exists():
            print(f"missing {r['id']}", file=sys.stderr)
            continue
        v = re.sub(r"\W", "_", r["id"])
        try:
            cols = load(con, f, v)
        except duckdb.Error as e:
            print(f"PARSE FAIL {r['id']}: {e}", file=sys.stderr)
            r["notes"] = f"parse failure: {str(e)[:200]}"
            continue
        s = con.execute(f"""SELECT count(*), count(DISTINCT camis),
              min(inspection_date) FILTER (WHERE inspection_date > DATE '1901-01-01'),
              max(inspection_date), max(record_date),
              count(*) FILTER (WHERE inspection_date IS NULL AND camis IS NOT NULL),
              count(*) FILTER (WHERE record_date IS NULL)
            FROM t_{v}""").fetchone()
        n, ncamis, dmin, dmax, rec, bad, norec = s
        r.update(bytes_gz=f.stat().st_size, rows=n, distinct_camis=ncamis,
                 min_insp_date=dmin or "", max_insp_date=dmax or "",
                 snapshot_date=rec or r.get("snapshot_date") or "",
                 has_latlng=int("latitude" in cols or "location_latitude" in cols),
                 has_bbl=int("bbl" in cols), has_bin=int("bin" in cols),
                 columns="|".join(cols))
        # notes: keep curated text, regenerate the automatic checks each run
        keep = [x for x in (r.get("notes") or "").split("; ")
                if x and not x.startswith(("parse failure", "AUTO:"))]
        if bad:
            keep.append(f"AUTO: {bad} rows with unparseable inspection date")
        if norec:  # RECORD DATE is a late column; nulls flag truncated/garbled rows
            keep.append(f"AUTO: {norec} rows missing record date (truncation/garbling check)")
        r["notes"] = "; ".join(keep)
        print(f"{r['id']:38s} rec={rec} rows={n:>8} camis={ncamis:>6} {dmin}..{dmax}")
        parts.append(f"SELECT *, DATE '{rec}' AS snapshot_date FROM t_{v}" if rec else
                     f"SELECT *, NULL::DATE AS snapshot_date FROM t_{v}")
    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    con.execute(f"CREATE TABLE allrows AS {' UNION ALL BY NAME '.join(parts)}")
    con.execute("""CREATE TABLE union_insp AS
        SELECT camis, inspection_date, arg_max(inspection_type, snapshot_date) AS inspection_type,
               arg_max(dba, snapshot_date) AS dba, arg_max(boro, snapshot_date) AS boro,
               arg_max(building, snapshot_date) AS building, arg_max(street, snapshot_date) AS street,
               arg_max(zipcode, snapshot_date) AS zipcode, arg_max(cuisine, snapshot_date) AS cuisine,
               arg_max(latitude, snapshot_date) AS latitude, arg_max(longitude, snapshot_date) AS longitude,
               arg_max(bbl, snapshot_date) AS bbl, arg_max(bin, snapshot_date) AS bin,
               arg_max(grade, snapshot_date) AS grade, arg_max(score, snapshot_date) AS score,
               min(snapshot_date) AS first_snapshot, max(snapshot_date) AS last_snapshot,
               count(DISTINCT snapshot_date) AS n_snapshots
        FROM allrows WHERE camis IS NOT NULL
        GROUP BY ALL""")
    con.execute(f"COPY union_insp TO '{RAW / 'union_inspections.parquet'}' (FORMAT parquet, COMPRESSION zstd)")
    tot = con.execute("SELECT count(DISTINCT camis) FROM union_insp").fetchone()[0]
    print(f"\nUNION distinct CAMIS: {tot}")
    cov = con.execute("""SELECT year(inspection_date) y, count(DISTINCT camis) camis,
            count(*) inspections FROM union_insp
        WHERE inspection_date BETWEEN DATE '2010-01-01' AND DATE '2026-12-31'
        GROUP BY 1 ORDER BY 1""").fetchall()
    with (RAW / "coverage_by_year.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "distinct_camis", "inspections"])
        w.writerows(cov)
    for y, c, i in cov:
        print(f"{y}: {c:>6} camis  {i:>7} inspections")

    # A restaurant that opened and closed entirely between two consecutive pulls
    # is invisible; so the meaningful gaps are between consecutive snapshot dates.
    snaps = sorted({str(r["snapshot_date"])[:10] for r in rows if r.get("snapshot_date")})
    gaps = sorted(((b2 - a2).days, a, b) for a, b in zip(snaps, snaps[1:])
                  for a2, b2 in [(date.fromisoformat(a), date.fromisoformat(b))])[::-1]
    print("\nlargest gaps between consecutive snapshots (days):")
    for d, a, b in gaps[:10]:
        print(f"  {d:>4}  {a} -> {b}")


if __name__ == "__main__":
    main()
