"""Collapse per-release snapshots into one row per place with first_seen / last_seen:
  data/raw/poi/fsq_all.parquet       one row per fsq_place_id
  data/raw/poi/overture_all.parquet  one row per linked Overture place

Overture ids were reset several times (fully at 2025-06-25 when GERS ids arrived), so Overture
rows are linked across releases with union-find over the Overture id and the upstream source
record ids (meta / Microsoft / Foursquare), which are stable. Latest attributes win.
extra gains n_releases, gone (absent from the newest release), statuses_seen, linked ids.
"""
from __future__ import annotations

import json

import pandas as pd

from poi_common import NORM_COLS, OUT, connect


def _newest(con, paths: list[str]):
    return con.sql(f"SELECT max(DATE (json_extract_string(extra,'release')[1:10])) FROM read_parquet({paths})").fetchone()[0]


def collapse_fsq(con) -> None:
    paths = [str(f) for f in sorted(OUT.glob("fsq_2*.parquet"))]
    if not paths:
        raise FileNotFoundError("no fsq_<release>.parquet files; run the fsq step first")
    newest = _newest(con, paths)
    out = OUT / "fsq_all.parquet"
    con.sql(f"""
    COPY (
      WITH u AS (SELECT *, DATE (json_extract_string(extra,'release')[1:10]) AS rel FROM read_parquet({paths})),
      agg AS (SELECT source_id, min(rel) fs, max(rel) ls, count(DISTINCT rel) n,
                     min(date_closed) FILTER (WHERE rel > (SELECT min(rel) FROM u)) AS any_closed
              FROM u GROUP BY 1),
      first_closed AS (SELECT source_id, bool_or(date_closed IS NOT NULL) closed_in_first FROM u
                       WHERE rel = (SELECT min(rel) FROM u) GROUP BY 1),
      latest AS (SELECT * FROM u QUALIFY row_number() OVER (PARTITION BY source_id ORDER BY rel DESC) = 1)
      SELECT l.source, l.source_id, l.name, l.category_raw, l.category, l.lat, l.lon, l.address,
             l.date_created, l.date_closed, a.fs AS first_seen, a.ls AS last_seen,
             json_merge_patch(l.extra::JSON, json_object(
               'n_releases', a.n, 'gone', a.ls < DATE '{newest}', 'newest_release', DATE '{newest}',
               'closed_during_window', l.date_closed IS NOT NULL AND NOT coalesce(f.closed_in_first, false)
             ))::VARCHAR AS extra
      FROM latest l JOIN agg a USING (source_id) LEFT JOIN first_closed f USING (source_id)
    ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)""")
    n, g = con.sql(f"SELECT count(*), count(*) FILTER (WHERE extra->>'gone' = 'true') FROM '{out}'").fetchone()
    print(f"  wrote {out.name}: {n:,} ids, {g:,} gone before newest release ({newest})")


class UF:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


LINK_DATASETS = {"meta": "m", "Microsoft": "x", "msft": "x", "Foursquare": "f"}


def collapse_overture(con) -> None:
    paths = [str(f) for f in sorted(OUT.glob("overture_2*.parquet"))]
    if not paths:
        raise FileNotFoundError("no overture_<release>.parquet files; run the overture step first")
    newest = _newest(con, paths)
    df = con.sql(f"""SELECT *, json_extract_string(extra,'release') AS release,
                            DATE (json_extract_string(extra,'release')[1:10]) AS rel
                     FROM read_parquet({paths})""").df()
    uf = UF()
    fsq_ids: dict[str, set] = {}
    for sid, ex in zip(df.source_id, df.extra):
        node = ("o", sid)
        uf.find(node)
        for s in json.loads(ex).get("sources") or []:
            tag = LINK_DATASETS.get(s.get("dataset"))
            rid = (s.get("record_id") or "").split("@")[0]
            if tag and rid:
                uf.union(node, (tag, rid))
                if tag == "f":
                    fsq_ids.setdefault(sid, set()).add(rid)
    df["key"] = [":".join(uf.find(("o", s))) for s in df.source_id]
    df = df.sort_values("rel")
    agg = df.groupby("key").agg(first_seen=("rel", "min"), last_seen=("rel", "max"),
                                n_releases=("release", "nunique"),
                                ids=("source_id", lambda s: sorted(set(s))))
    latest = df.drop_duplicates("key", keep="last").set_index("key")
    status = df.assign(st=[json.loads(e).get("operating_status") for e in df.extra]) \
               .dropna(subset=["st"]).groupby("key").st.agg(lambda s: sorted(set(s)))
    out = latest[["source", "source_id", "name", "category_raw", "category", "lat", "lon", "address",
                  "date_created", "date_closed"]].join(agg)
    extras = []
    for k, ex in zip(out.index, latest.extra):
        e = json.loads(ex)
        e.pop("sources", None)
        a = agg.loc[k]
        fs = sorted(set().union(*[fsq_ids.get(i, set()) for i in a.ids]))
        e.update({"n_releases": int(a.n_releases), "gone": bool(pd.Timestamp(a.last_seen) < pd.Timestamp(newest)),
                  "newest_release": str(newest), "statuses_seen": status.get(k, []),
                  "overture_ids": a.ids[-5:], "n_overture_ids": len(a.ids), "fsq_ids": fs})
        extras.append(json.dumps(e))
    out["extra"] = extras
    out = out[NORM_COLS[:-1] + ["extra"]].copy()
    out["first_seen"] = pd.to_datetime(out.first_seen).dt.date
    out["last_seen"] = pd.to_datetime(out.last_seen).dt.date
    dest = OUT / "overture_all.parquet"
    con.register("_out", out.reset_index(drop=True))
    con.sql(f"""COPY (SELECT * REPLACE (date_created::DATE AS date_created, date_closed::DATE AS date_closed)
                FROM _out) TO '{dest}' (FORMAT parquet, COMPRESSION zstd)""")
    gone = sum(json.loads(e)["gone"] for e in extras)
    print(f"  wrote {dest.name}: {len(out):,} linked places from {df.source_id.nunique():,} ids, "
          f"{gone:,} gone before newest release ({newest})")


def run() -> None:
    con = connect()
    collapse_fsq(con)
    collapse_overture(con)
