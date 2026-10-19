"""Michelin Guide NYC stars by guide year (2006 -> latest) from Wikipedia.

Source: en.wikipedia.org "List of Michelin-starred restaurants in New York City"
(CC BY-SA). One row per restaurant x guide year with stars 0-3, or status
'closed' / 'temp_closed' / 'none'. Also pulls NYC Bib Gourmand rows if the US
Bib Gourmand list has a New York section.
"""
from __future__ import annotations

import re

import pandas as pd

import ratings_common as rc

PAGE = "List_of_Michelin-starred_restaurants_in_New_York_City"
BIB_PAGE = "List_of_Michelin_Bib_Gourmand_restaurants_in_the_United_States"


def _cell_value(raw: str) -> tuple[int | None, str]:
    m = re.search(r"stars=(\w+)", raw)
    if m:
        v = m.group(1)
        if v.isdigit():
            return int(v), "starred"
        return None, {"none": "none", "closed": "closed"}.get(v, v)
    if "emporarily" in raw:
        return None, "temp_closed"
    return None, "none" if not rc.clean(raw) else rc.clean(raw).lower()


def _borough(loc: str) -> str | None:
    for b in ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]:
        if b in loc:
            return b
    return None


def stars() -> pd.DataFrame:
    text = rc.wiki_raw(PAGE)
    rows = []
    for table in rc.wikitables(text):
        header = [rc.clean(t) for t in rc.expand(table[0])]
        years = [(i, int(h)) for i, h in enumerate(header) if re.fullmatch(r"(19|20)\d\d", h)]
        if not years:
            continue
        for r in table[1:]:
            cells = rc.expand(r)
            name = rc.clean(cells[0]) if cells else ""
            if not name or name.lower().startswith("reference") or len(cells) < len(header):
                continue
            loc = rc.clean(cells[2])
            for i, y in years:
                n, status = _cell_value(cells[i])
                rows.append({"name": name, "cuisine": rc.clean(cells[1]), "location": loc,
                             "borough": _borough(loc),
                             "neighborhood": loc.split("–")[-1].strip() if "–" in loc else loc,
                             "year": y, "stars": n, "status": status})
    df = pd.DataFrame(rows)
    df["list"] = "michelin_stars"
    return df


def bib() -> pd.DataFrame:
    """NYC Bib Gourmand rows from the US list (if its NYC section has year columns)."""
    text = rc.wiki_raw(BIB_PAGE)
    m = re.search(r"==\s*New York[^=]*==(.*?)(?=\n==[^=])", text, re.S)
    if not m:
        print("bib: no New York section found on", BIB_PAGE)
        return pd.DataFrame()
    rows = []
    for table in rc.wikitables(m.group(1)):
        header = [rc.clean(t) for t in rc.expand(table[0])]
        years = [(i, int(h)) for i, h in enumerate(header) if re.fullmatch(r"(19|20)\d\d", h)]
        if not years:
            continue
        for r in table[1:]:
            cells = rc.expand(r)
            if len(cells) < len(header):
                continue
            name = rc.clean(cells[0])
            loc = rc.clean(cells[2]) if len(cells) > 2 else ""
            for i, y in years:
                raw = cells[i]
                on = bool(re.search(r"bib|yes|✓|\{\{(Y|y)", raw, re.I)) and "none" not in raw.lower()
                rows.append({"name": name, "cuisine": rc.clean(cells[1]), "location": loc,
                             "borough": _borough(loc), "year": y,
                             "stars": None, "status": "bib" if on else rc.clean(raw).lower() or "none"})
    df = pd.DataFrame(rows)
    if len(df):
        df["list"] = "michelin_bib"
    return df


def run() -> pd.DataFrame:
    df = stars()
    b = bib()
    if len(b):
        df = pd.concat([df, b], ignore_index=True)
    c = rc.connect()
    keys = df[["name", "borough"]].drop_duplicates().reset_index(drop=True)
    keys["rid"] = keys.index
    # year hint = first year it held a star, so the right CAMIS is preferred
    first = (df[df.stars.fillna(0) > 0].groupby(["name", "borough"], dropna=False).year.min()
             .rename("year").reset_index())
    keys = keys.merge(first, on=["name", "borough"], how="left")
    m = rc.match_name(c, keys, "rid", boro_col="borough")
    keys = keys.drop(columns="year").merge(m, on="rid", how="left")
    df = df.merge(keys, on=["name", "borough"], how="left").drop(columns="rid")
    df["source"] = "wikipedia:" + PAGE
    rc.write(df, "michelin_nyc")
    starred = keys.merge(df[df.stars.fillna(0) > 0][["name", "borough"]].drop_duplicates())
    print(f"michelin: {starred.shape[0]} starred restaurants, years {df.year.min()}-{df.year.max()}, "
          f"CAMIS match {starred.camis.notna().mean():.0%}")
    return df



# ---------- full Michelin Guide selection (stars + Bib Gourmand + "Selected") ----------
# github.com/ngshiheng/michelin-my-maps (MIT): a scrape of guide.michelin.com kept in git,
# so its history gives dated snapshots (2022-07 -> now). One snapshot per quarter.
MMM_REPO = "ngshiheng/michelin-my-maps"
MMM_PATH = "data/michelin_my_maps.csv"


def guide_snapshots() -> pd.DataFrame:
    import io
    commits = []
    for page in range(1, 5):
        r = rc.get(f"https://api.github.com/repos/{MMM_REPO}/commits",
                   params={"path": MMM_PATH, "per_page": 100, "page": page})
        batch = r.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"GitHub API error: {str(batch)[:200]}")
        commits += [(x["sha"], x["commit"]["committer"]["date"][:10]) for x in batch]
        if len(batch) < 100:
            break
    cm = pd.DataFrame(commits, columns=["sha", "date"])
    cm["q"] = pd.PeriodIndex(pd.to_datetime(cm.date), freq="Q").astype(str)
    pick = cm.sort_values("date").groupby("q").tail(1)
    frames = []
    for _, row in pick.iterrows():
        txt = rc.get(f"https://raw.githubusercontent.com/{MMM_REPO}/{row.sha}/{MMM_PATH}").text
        d = pd.read_csv(io.StringIO(txt), dtype=str)
        d = d[d.Location.fillna("").str.contains("New York") &
              pd.to_numeric(d.Latitude, errors="coerce").between(40.49, 40.92) &
              pd.to_numeric(d.Longitude, errors="coerce").between(-74.27, -73.68)]
        keep = [c for c in ["Name", "Address", "Location", "Price", "Cuisine", "Longitude", "Latitude",
                            "Url", "WebsiteUrl", "Award", "GreenStar"] if c in d]
        d = d[keep].copy()  # drop Michelin's description text (copyrighted prose)
        d["snapshot"] = row.date
        d["commit"] = row.sha
        frames.append(d)
        print(f"  michelin guide {row.date}: {len(d)} NYC rows")
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    df = df.rename(columns={"longitude": "lon", "latitude": "lat", "websiteurl": "website"})
    df["lat"] = df.lat.astype(float)
    df["lon"] = df.lon.astype(float)
    df["snapshot"] = pd.to_datetime(df.snapshot)
    a = df.award.fillna("")
    df["stars"] = pd.to_numeric(a.str.extract(r"(\d) (?:MICHELIN )?Star", expand=False), errors="coerce")
    df["award_level"] = (df.stars.map(lambda x: f"{int(x)}_star" if x == x else None)
                         .fillna(a.map(lambda t: "bib" if "Bib" in t else "selected" if "Selected" in t else None)))
    df["green_star"] = a.str.contains("Green") | (df.greenstar.fillna("0") == "1")
    c = rc.connect()
    places = df.drop_duplicates("url")[["url", "name", "lat", "lon"]].reset_index(drop=True)
    places["pid"] = places.index
    m = rc.match_geo(c, places, "pid")
    places = places.merge(m, on="pid", how="left").drop(columns=["pid", "name", "lat", "lon"])
    df = df.merge(places, on="url", how="left")
    df["source"] = f"github:{MMM_REPO}"
    rc.write(df, "michelin_guide_nyc_snapshots")
    u = df.drop_duplicates("url")
    print(f"michelin guide: {len(u)} NYC venues over {df.snapshot.nunique()} snapshots; "
          f"CAMIS match {u.camis.notna().mean():.0%}; awards: {df.award.value_counts().to_dict()}")
    return df


if __name__ == "__main__":
    run()
    guide_snapshots()
