"""Foursquare check-in research datasets -> NYC food & drink venues.

  tsmc2014  Dingqi Yang et al., "NYC and Tokyo Check-in Dataset" (IEEE TSMC 2015),
            2012-04-12 -> 2013-02-16, 227k NYC check-ins with real Foursquare venue
            ids, category, lat/lon. Google Drive copy (the IMT mirror is very slow).
            No license stated; citation requested.
  lbsn2vec  Yang et al., LBSN2Vec++ (WWW 2019 / TKDE 2020), 4TU.ResearchData,
            CC BY 4.0. "Raw" set: 90M check-ins, 11.2M venues, 2012-04 -> 2014-01.
            Two members of a 2.68 GB remote zip are streamed with HTTP Range
            requests; only NYC food/drink rows are kept.
  msteps    Massive-STEPS New York (Hugging Face CRUISEResearchGroup, Apache-2.0),
            built from the CC0 Semantic Trails datasets (2012-13 and 2017-18) and
            enriched with Foursquare OS Places names/coordinates.

Venue names for tsmc2014 / lbsn2vec come from our Foursquare OS Places copy
(data/raw/poi/fsq_all.parquet), which keeps legacy 24-hex venue ids. Venues not in
FSQ OS keep coordinates + category but no name (they cannot be name-matched).
Outputs: research_poi/<source>_venues.parquet, <source>_yearly.parquet
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd

import rpoi_common as rc

TSMC_ID = "1VE67jfSN-GV6fkCfuyBEQJzk_qy-SfOk"
LBSN_URL = "https://data.4tu.nl/file/882bd9c5-5821-48b6-9b35-5c9551dd04ca/08f9ede1-8a8b-4036-88b5-2c723efc3141"
MSTEPS_URL = ("https://huggingface.co/datasets/CRUISEResearchGroup/Massive-STEPS-New-York/"
              "resolve/main/new_york_checkins.csv")
FSQ_FOOD = rc.FOOD + r"|burrito|poke|cafeteria|fish & chips|sake|whisky|distillery|winery"
FSQ_NOT = rc.NOT_FOOD + r"|home \(private\)|office|food & drink shop|gourmet shop|farmers market"


def is_food(cat: str) -> bool:
    return bool(cat) and re.search(FSQ_FOOD, cat) is not None and re.search(FSQ_NOT, cat) is None


def local_date(utc: str, offset_min: str):
    t = datetime.strptime(utc, "%a %b %d %H:%M:%S +0000 %Y")
    return (t + timedelta(minutes=int(offset_min))).date()


def attach_fsq_names(c, table: str) -> None:
    """Add name/address/fsq dates from FSQ OS by legacy venue id; keep dataset coords."""
    c.execute(f"""
    create or replace temp table {table} as
    select t.*, f.name, f.address, f.date_created fsq_date_created, f.date_closed fsq_date_closed
    from {table} t left join (
      select source_id, name, address, date_created, date_closed
      from '{rc.RAW / 'poi' / 'fsq_all.parquet'}'
      qualify row_number() over (partition by source_id order by last_seen desc) = 1
    ) f on f.source_id = t.venue_id""")
    n, named = c.execute(f"select count(*), count(name) from {table}").fetchone()
    print(f"  {table}: {named:,} of {n:,} venues named via FSQ OS ({named / max(n, 1):.0%})")


def run_tsmc() -> None:
    z = rc.download(rc.gdrive_url(TSMC_ID), rc.DL / "tsmc2014.zip")
    zf = zipfile.ZipFile(z)
    member = next(n for n in zf.namelist() if n.endswith("TSMC2014_NYC.txt"))
    venues, daily = {}, Counter()
    with zf.open(member) as f:
        for line in io.TextIOWrapper(f, encoding="latin-1"):
            p = line.rstrip("\n").split("\t")
            if len(p) != 8:
                raise ValueError(f"tsmc2014: unexpected row {line[:120]!r}")
            _, vid, _, cat, lat, lon, off, utc = p
            if not is_food(cat):
                continue
            venues.setdefault(vid, (vid, cat, float(lat), float(lon)))
            daily[(vid, local_date(utc, off))] += 1
    c = rc.connect()
    rc.df_to(c, pd.DataFrame(venues.values(), columns=["venue_id", "category", "lat", "lon"]), "v")
    rc.df_to(c, pd.DataFrame([(k[0], k[1], n) for k, n in daily.items()], columns=["venue_id", "d", "n"]), "a")
    c.execute("alter table a alter d type date")
    rc.clip_boroughs(c, "v")
    attach_fsq_names(c, "v")
    rc.write_venues(c, "tsmc2014", "v", "a")
    z.unlink()


def run_lbsn() -> None:
    zf = zipfile.ZipFile(io.BufferedReader(rc.HttpRangeFile(LBSN_URL), 1 << 20))
    names = zf.namelist()
    poi = next(n for n in names if n.endswith("/raw_POIs.txt"))
    chk = next(n for n in names if n.endswith("/raw_Checkins_anonymized.txt"))
    venues = {}
    n = 0
    print("  streaming", poi)
    with zf.open(poi) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
            n += 1
            p = line.rstrip("\n").split("\t")
            if len(p) < 5 or p[4] != "US":
                continue
            try:
                lat, lon = float(p[1]), float(p[2])
            except ValueError:
                continue
            if rc.in_bbox(lat, lon) and is_food(p[3]):
                venues[p[0]] = (p[0], p[3], lat, lon)
    print(f"  POIs scanned {n:,}; NYC-bbox food/drink {len(venues):,}")
    daily = Counter()
    n = 0
    print("  streaming", chk, "(~1.9 GB compressed)")
    with zf.open(chk) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
            n += 1
            if n % 10_000_000 == 0:
                print(f"    {n:,} check-ins scanned, {sum(daily.values()):,} kept")
            p = line.split("\t")
            if len(p) == 4 and p[1] in venues:
                daily[(p[1], local_date(p[2], p[3]))] += 1
    print(f"  check-ins scanned {n:,}; kept {sum(daily.values()):,}")
    c = rc.connect()
    rc.df_to(c, pd.DataFrame(venues.values(), columns=["venue_id", "category", "lat", "lon"]), "v")
    rc.df_to(c, pd.DataFrame([(k[0], k[1], m) for k, m in daily.items()], columns=["venue_id", "d", "n"]), "a")
    c.execute("alter table a alter d type date")
    rc.clip_boroughs(c, "v")
    attach_fsq_names(c, "v")
    rc.write_venues(c, "lbsn2vec", "v", "a")


def run_msteps() -> None:
    p = rc.download(MSTEPS_URL, rc.DL / "msteps_new_york_checkins.csv")
    c = rc.connect()
    c.execute(f"""
    create temp table raw as
    select * from read_csv('{p}', header=true, all_varchar=true)""")
    c.execute("""
    create temp table v as
    select 'ms' || venue_id as venue_id, any_value(name) as name, any_value(address) as address,
           any_value(venue_category) as category,
           any_value(try_cast(latitude as double)) as lat, any_value(try_cast(longitude as double)) as lon,
           list_distinct(list(split_part(trail_id, '_', 1))) as std_release
    from raw group by venue_id""")
    rows = c.execute("select venue_id, category from v").fetchall()
    keep = [vid for vid, cat in rows if is_food(cat or "")]
    rc.df_to(c, pd.DataFrame({"venue_id": keep}), "keep")
    c.execute("delete from v where venue_id not in (select venue_id from keep)")
    c.execute("""
    create temp table a as
    select 'ms' || venue_id as venue_id, try_cast("timestamp" as timestamp)::date as d, count(*) as n
    from raw where 'ms' || venue_id in (select venue_id from v) group by 1, 2""")
    bad = c.execute("select count(*) from a where d is null").fetchone()[0]
    if bad:
        print(f"  msteps: {bad:,} venue-days with unparsable timestamps dropped")
        c.execute("delete from a where d is null")
    rc.clip_boroughs(c, "v")
    rc.write_venues(c, "msteps", "v", "a")
    p.unlink()


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["tsmc", "msteps", "lbsn"]:
        {"tsmc": run_tsmc, "msteps": run_msteps, "lbsn": run_lbsn}[s]()
