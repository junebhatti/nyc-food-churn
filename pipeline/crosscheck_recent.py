"""Cross-check recent DOHMH status against the other sources.

For each DOHMH restaurant, look for a place in another source within MAX_M
metres whose normalized name is similar. Reports how often the sources agree on
(a) places DOHMH says are open now and (b) places DOHMH recently dropped.

Run: .venv/bin/python pipeline/crosscheck_recent.py
"""
import duckdb

RAW = "data/raw"
MAX_M = 80
NAME_SIM = 0.85
LIVE = "2026-10-16"

c = duckdb.connect()

# Strip punctuation and filler words so "JOE'S PIZZA INC" ~ "Joe's Pizza".
c.execute(r"""
create macro norm(s) as trim(regexp_replace(
  regexp_replace(upper(coalesce(s, '')), '[^A-Z0-9 ]', '', 'g'),
  '\b(THE|INC|LLC|CORP|RESTAURANT|RESTAURANTS|CAFE|BAR|AND|NYC|NY)\b', '', 'g'))
""")
c.execute("""
create macro dist_m(lat1, lon1, lat2, lon2) as
  111320 * sqrt(power(lat1 - lat2, 2) + power((lon1 - lon2) * cos(radians(lat1)), 2))
""")

# Latest row per CAMIS that has coordinates.
c.execute(f"""
create table dohmh as
select camis, dba, cuisine, last_snapshot, nullif(regexp_replace(bin, '\.0$', ''), '') bin,
       try_cast(latitude as double) lat, try_cast(longitude as double) lon
from '{RAW}/dohmh/union_inspections.parquet'
where try_cast(latitude as double) between 40.4 and 41.0
qualify row_number() over (partition by camis order by inspection_date desc) = 1
""")
c.execute(f"create table open_now as select * from dohmh where last_snapshot = '{LIVE}'")
# Dropped from the live data during the last ~16 months: likely closures.
c.execute(f"""
create table dropped as select * from dohmh
where last_snapshot between '2025-06-01' and '2026-04-30'
""")

c.execute(f"""
create table others as
select 'overture' src, name, lat, lon,
       coalesce(json_extract_string(extra, '$.operating_status'), 'unknown') status
from '{RAW}/poi/overture_2026-09-23.0.parquet'
union all
select 'osm', name, lat, lon, 'open' from '{RAW}/poi/osm_overpass.parquet'
union all
select 'foursquare', name, lat, lon,
       case when date_closed is null then 'open' else 'permanently_closed' end
from (select * from '{RAW}/poi/fsq_all.parquet'
      qualify row_number() over (partition by source_id order by last_seen desc) = 1)
union all
select 'liquor', coalesce(dba, legal_name), lat, lon,
       case when in_current_lists and end_date is null then 'open' else 'permanently_closed' end
from '{RAW}/gov/sla_licenses_nyc.parquet' where on_premises and lat is not null
""")
c.execute("alter table others add column cell_lat int; alter table others add column cell_lon int")
c.execute("update others set cell_lat = floor(lat * 1000), cell_lon = floor(lon * 1000)")


def match(table):
    """Best name match per (CAMIS, source) within MAX_M metres."""
    return c.execute(f"""
    with d as (select *, floor(lat * 1000)::int cl, floor(lon * 1000)::int cn from {table}),
    pairs as (
      select d.camis, o.src, o.status,
             jaro_winkler_similarity(norm(d.dba), norm(o.name)) sim
      from d join others o
        on o.cell_lat between d.cl - 1 and d.cl + 1
       and o.cell_lon between d.cn - 1 and d.cn + 1
      where dist_m(d.lat, d.lon, o.lat, o.lon) <= {MAX_M}
    )
    select camis, src, arg_max(status, sim) status, max(sim) sim
    from pairs where sim >= {NAME_SIM} group by 1, 2
    """).df()


def report(table, label):
    n = c.execute(f"select count(*) from {table}").fetchone()[0]
    m = match(table)
    print(f"\n== {label}: {n:,} DOHMH places ==")
    for src, g in m.groupby("src"):
        counts = g["status"].value_counts().to_dict()
        print(f"  {src:<10} matched {len(g):>6,} ({len(g) / n:5.1%})  status: {counts}")
    any_src = m["camis"].nunique()
    print(f"  matched in at least one source: {any_src:,} ({any_src / n:.1%})")
    return m


open_m = report("open_now", "Open per live DOHMH (2026-10-16)")
report("dropped", "Dropped from DOHMH Jun 2025 – Apr 2026")

# Is a drop a closure? A dropped CAMIS can reappear as a new CAMIS at the same
# spot (new owner / re-permit), or be replaced by a different business.
for t in ("open_now", "dropped"):
    c.execute(f"alter table {t} add column cl int; alter table {t} add column cn int")
    c.execute(f"update {t} set cl = floor(lat * 1000), cn = floor(lon * 1000), dba = norm(dba)")
# Same building = same BIN; placeholder BINs (x000000) are skipped.
fate = c.execute("""
with p as (
  select d.camis,
         max(jaro_winkler_similarity(o.dba, d.dba)) best_sim
  from dropped d join open_now o
    on o.bin = d.bin and o.camis <> d.camis and d.bin not like '_000000'
  group by 1
)
select case when d.bin is null or d.bin like '_000000' then 'no building id'
            when best_sim >= 0.85 then 'same name, new permit'
            when best_sim is not null then 'different business in building now'
            else 'no food business in building now' end fate,
       count(*) n
from dropped d left join p using (camis) group by 1 order by n desc
""").df()
print("\n== What is at the spot of each dropped DOHMH place now ==")
print(fate.to_string(index=False))

print("\n== Sample of open DOHMH places matched in no other source ==")
c.register("open_m", open_m)
for row in c.execute("""
  select dba, cuisine from open_now
  where camis not in (select camis from open_m) using sample 20 rows (reservoir, 7)
""").fetchall():
    print("  ", row)

# Reverse: open Overture food places with no DOHMH place (open or recently
# dropped) nearby by name. Shows what DOHMH structurally misses.
miss = c.execute(f"""
with o as (
  select name, category_raw, lat, lon from '{RAW}/poi/overture_2026-09-23.0.parquet'
  where json_extract_string(extra, '$.operating_status') = 'open'
    and category in ('restaurant', 'bar', 'cafe_coffee', 'bakery_dessert')
),
d as (select * from dohmh where last_snapshot >= '2025-06-01')
select o.category_raw,
       count(*) n,
       count(*) filter (where not exists (
         select 1 from d
         where abs(d.lat - o.lat) < 0.001 and abs(d.lon - o.lon) < 0.0013
           and dist_m(d.lat, d.lon, o.lat, o.lon) <= {MAX_M}
           and jaro_winkler_similarity(norm(d.dba), norm(o.name)) >= {NAME_SIM})) unmatched
from o group by 1 order by n desc limit 15
""").df()
miss["unmatched_pct"] = (miss.unmatched / miss.n).round(2)
print("\n== Open Overture food places with no DOHMH match, by category ==")
print(miss.to_string(index=False))
