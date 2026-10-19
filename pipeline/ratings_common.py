"""Shared helpers for the ratings / critics pipeline (pipeline/fetch_ratings.py).

- polite HTTP GET with a descriptive User-Agent and a delay
- Wikipedia raw wikitext fetch + a small wikitable parser (no lxml in .venv)
- DOHMH CAMIS matching: name similarity within 80 m when we have coordinates,
  otherwise normalized-name match inside the same borough.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "ratings"
DOHMH = RAW / "dohmh" / "union_inspections.parquet"
UA = "nyc-food-churn research script (personal, non-commercial; polite rate)"
MAX_M = 80
NAME_SIM = 0.85

_session = requests.Session()
_session.headers["User-Agent"] = UA
_last = [0.0]


def get(url: str, delay: float = 1.0, **kw) -> requests.Response:
    """GET with at least `delay` seconds between calls; raises on HTTP errors."""
    wait = delay - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            r = _session.get(url, timeout=60, **kw)
            _last[0] = time.time()
            if r.status_code in (429, 503) and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.ConnectionError as e:
            if attempt == 2:
                raise RuntimeError(f"GET failed after retries: {url}") from e
            time.sleep(5)
    raise RuntimeError(f"GET failed: {url} (HTTP {r.status_code})")


def wiki_raw(title: str) -> str:
    return get("https://en.wikipedia.org/w/index.php",
               params={"title": title, "action": "raw"}).text


# ---------- wikitext ----------
_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S)


def clean(s: str) -> str:
    """Wikitext cell -> plain text (links, templates, refs, markup removed)."""
    s = _REF.sub("", s)
    s = re.sub(r"\{\{(?:sort|sortname)\|[^|}]*\|([^}]*)\}\}", r"\1", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip()


def wikitables(text: str) -> list[list[list[tuple[str, int]]]]:
    """Return tables -> rows -> cells as (raw_cell_text, colspan). Header rows included."""
    tables = []
    for m in re.finditer(r"^\{\|.*?^\|\}", text, re.S | re.M):
        rows, cur = [], []
        for line in m.group(0).splitlines()[1:]:
            line = line.rstrip()
            if line.startswith("|-") or line.startswith("|}"):
                if cur:
                    rows.append(cur)
                cur = []
                continue
            if line.startswith("|+") or not line:
                continue
            if line[0] in "!|":
                sep = "!!" if line[0] == "!" else "||"
                for part in line[1:].split(sep):
                    span = 1
                    # attribute prefix like: colspan="2" | text   or  scope="row"| text
                    am = re.match(r'\s*((?:[a-z]+="[^"]*"\s*)+)\|(?!\|)(.*)$', part, re.S)
                    if am:
                        cs = re.search(r'colspan="?(\d+)', am.group(1))
                        span = int(cs.group(1)) if cs else 1
                        part = am.group(2)
                    else:
                        cs = re.match(r'\s*colspan="?(\d+)"?\s*(.*)$', part, re.S)
                        if cs:
                            span, part = int(cs.group(1)), cs.group(2)
                    cur.append((part.strip(), span))
            elif cur:  # continuation line of previous cell
                txt, sp = cur[-1]
                cur[-1] = (txt + " " + line, sp)
        if cur:
            rows.append(cur)
        tables.append(rows)
    return tables


def expand(row: list[tuple[str, int]]) -> list[str]:
    out = []
    for txt, span in row:
        out.extend([txt] * span)
    return out


# ---------- DOHMH matching ----------
BORO = {"MANHATTAN": "Manhattan", "BROOKLYN": "Brooklyn", "QUEENS": "Queens",
        "BRONX": "Bronx", "STATEN ISLAND": "Staten Island", "1": "Manhattan",
        "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}


def connect() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(r"""
    create macro norm(s) as trim(regexp_replace(regexp_replace(
      regexp_replace(upper(strip_accents(coalesce(s, ''))), '&', ' AND ', 'g'),
      '[^A-Z0-9 ]', '', 'g'),
      '\b(THE|INC|LLC|CORP|RESTAURANT|RESTAURANTS|CAFE|BAR|AND|NYC|NY)\b', '', 'g'))
    """)
    c.execute("""
    create macro dist_m(lat1, lon1, lat2, lon2) as
      111320 * sqrt(power(lat1 - lat2, 2) + power((lon1 - lon2) * cos(radians(lat1)), 2))
    """)
    return c


def load_dohmh(c: duckdb.DuckDBPyConnection) -> None:
    """One row per CAMIS: latest name/coords, first/last inspection, borough."""
    if c.execute("select count(*) from information_schema.tables where table_name='dohmh'").fetchone()[0]:
        return
    c.execute(f"""
    create table dohmh as
    select camis, arg_max(dba, inspection_date) dba, arg_max(boro, inspection_date) boro,
           arg_max(building || ' ' || street, inspection_date) address,
           arg_max(try_cast(latitude as double), case when try_cast(latitude as double) between 40.4 and 41.0 then inspection_date end) lat,
           arg_max(try_cast(longitude as double), case when try_cast(latitude as double) between 40.4 and 41.0 then inspection_date end) lon,
           min(inspection_date) first_insp, max(inspection_date) last_insp,
           max(last_snapshot) last_snapshot
    from '{DOHMH}' group by camis
    """)
    c.execute("alter table dohmh add column nname varchar")
    c.execute("update dohmh set nname = norm(dba)")
    c.execute("""update dohmh set boro = case upper(boro) when '1' then 'MANHATTAN' when '2' then 'BRONX'
                 when '3' then 'BROOKLYN' when '4' then 'QUEENS' when '5' then 'STATEN ISLAND'
                 else upper(boro) end""")


def match_geo(c, df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """df needs id_col, name, lat, lon. Returns id_col, camis, match_sim, match_m."""
    load_dohmh(c)
    c.register("_src", df[[id_col, "name", "lat", "lon"]])
    res = c.execute(f"""
    with s as (select {id_col} id, norm(name) nn, lat, lon from _src where lat is not null),
    d as (select camis, nname, lat, lon from dohmh where lat is not null),
    pairs as (
      select s.id, d.camis, jaro_winkler_similarity(s.nn, d.nname) sim,
             dist_m(s.lat, s.lon, d.lat, d.lon) m
      from s join d on d.lat between s.lat - 0.0008 and s.lat + 0.0008
                   and d.lon between s.lon - 0.0011 and s.lon + 0.0011
      where s.nn <> '' and d.nname <> '')
    select id {id_col}, arg_max(camis, sim) camis, max(sim) match_sim, arg_max(m, sim) match_m
    from pairs where m <= {MAX_M} and sim >= {NAME_SIM} group by id
    """).df()
    c.unregister("_src")
    return res


def match_name(c, df: pd.DataFrame, id_col: str, boro_col: str | None = None,
               min_sim: float = 0.95) -> pd.DataFrame:
    """Name-only match (lists with no coordinates). Exact normalized name first,
    else best Jaro-Winkler >= min_sim; restricted to borough when given.
    Picks the CAMIS whose inspection years best cover the list year if `year` exists."""
    load_dohmh(c)
    cols = [id_col, "name"] + ([boro_col] if boro_col else []) + (["year"] if "year" in df else [])
    src = df[cols].rename(columns={id_col: "id"}).copy()
    if boro_col:
        src = src.rename(columns={boro_col: "sboro"})
        src["sboro"] = src["sboro"].str.upper()
    else:
        src["sboro"] = None
    if "year" not in src:
        src["year"] = None
    c.register("_src", src)
    # Compare with spaces removed ("JO JO" = "JOJO"). A prefix match ("DEL POSTO" ->
    # "DEL POSTO RISTORANTE") counts as 0.9; JW alone must reach min_sim.
    res = c.execute(f"""
    with s as (select id, replace(norm(name), ' ', '') nn, sboro, try_cast(year as int) yr from _src),
    d as (select *, replace(nname, ' ', '') nn from dohmh),
    pairs as (
      select s.id, d.camis,
             jaro_winkler_similarity(s.nn, d.nn) jw,
             least(length(s.nn), length(d.nn)) >= 5
               and (least(length(s.nn), length(d.nn)) >= 6
                    or least(length(s.nn), length(d.nn)) * 2 >= greatest(length(s.nn), length(d.nn)))
               and (starts_with(d.nn, s.nn) or starts_with(s.nn, d.nn)) is_prefix,
             -- prefer a CAMIS inspected around the list year
             case when s.yr is null then 0
                  when s.yr between year(d.first_insp) - 1 and year(d.last_insp) + 1 then 1 else 0 end yr_ok
      from s join d on (s.sboro is null or d.boro = s.sboro)
      where length(s.nn) >= 3 and (s.sboro is not null or {'false' if boro_col else 'true'}))
    , ok as (select *, case when jw >= {min_sim} then jw else 0.9 end sim
             from pairs where jw >= {min_sim} or is_prefix)
    select id, arg_max(camis, sim + yr_ok) camis, max(sim) match_sim,
           count(distinct camis) n_candidates
    from ok group by id
    """).df().rename(columns={"id": id_col})
    c.unregister("_src")
    return res


def write(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.parquet"
    df.to_parquet(p, index=False)
    print(f"wrote {p.relative_to(ROOT)}: {len(df):,} rows")
    return p
