"""Awards with NYC restaurants: James Beard (winners, 2010 -> latest) and
The World's 50 Best Restaurants (ranks 1-50, and 51-100 where published).

- James Beard: Wikipedia "James Beard Foundation Award: 2010s" / "2020s" (CC BY-SA),
  bullets under the Chef & Restaurant sections that name a NYC borough / "New York".
  Winners only; nominees/semifinalists are on jamesbeard.org (not pulled).
- 50 Best: the50.com public "previous lists" page (one page holds every year), fetched once.
"""
from __future__ import annotations

import re

import pandas as pd

import ratings_common as rc

JBF_PAGES = ["James_Beard_Foundation_Award:_2010s", "James_Beard_Foundation_Award:_2020s"]
NYC_RE = re.compile(r"New York(?:,| City)|Brooklyn|Queens|Bronx|Staten Island|Manhattan")
# categories whose first field is the venue itself (else: "Person, Venue, City")
VENUE_FIRST = re.compile(r"(?i)^(outstanding )?(restaurant|new restaurant|best new restaurant|service|"
                         r"hospitality|bar|wine program|outstanding bar|outstanding wine)")
W50_URL = "https://www.the50.com/restaurants/best-in-the-world/previous-list/2019"


def _boro(text: str) -> str | None:
    for b in ["Brooklyn", "Queens", "Bronx", "Staten Island"]:
        if b in text:
            return b
    return "Manhattan" if re.search(r"New York|Manhattan", text) else None


def jbf() -> pd.DataFrame:
    rows = []
    for page in JBF_PAGES:
        text = rc.wiki_raw(page)
        for ym in re.finditer(r"^==\s*(\d{4}) awards?\s*==(.*?)(?=^==\s*\d{4}|\Z)", text, re.S | re.M):
            year = int(ym.group(1))
            for sec in re.finditer(r"^===\s*([^=]+?)\s*===(.*?)(?=^===|\Z)", ym.group(2), re.S | re.M):
                if not re.search(r"(?i)chef|restaurant", sec.group(1)) or "Design" in sec.group(1):
                    continue
                for line in sec.group(2).splitlines():
                    if not line.startswith("*"):
                        continue
                    t = rc.clean(line.lstrip("* "))
                    if not NYC_RE.search(t) or ":" not in t:
                        continue
                    cat, rest = re.split(r"\s*[:\-–]\s+", t, maxsplit=1) if re.search(r":\s", t) else (t, "")
                    if cat.startswith("Best Chef") and " - " in rest:  # "Best Chef: New York State - X, Y"
                        sub, rest = rest.split(" - ", 1)
                        cat = f"{cat}: {sub}"
                    parts = [p.strip() for p in rest.split(",") if p.strip()]
                    parts = [p for p in parts if not re.fullmatch(
                        r"(New York( City)?|NY|N\.Y\.|Brooklyn|Queens|Bronx|Staten Island|Manhattan)\.?", p)]
                    if not parts or re.search(r"(?i)design|graphics|professional", cat):
                        continue  # design firms / beverage people, not venues
                    if VENUE_FIRST.search(cat) or len(parts) == 1:
                        venue, person = parts[0], None
                    else:
                        person, venue = parts[0], parts[1]
                    venue = re.sub(r"(?i)^(chef/?owner|chef/partners?):.*", "", venue).strip()
                    rows.append({"name": venue, "person": person, "year": year,
                                 "list": "james_beard", "award": cat, "rating": "winner",
                                 "borough": _boro(t), "raw": t})
    return pd.DataFrame(rows)


def w50() -> pd.DataFrame:
    h = rc.get(W50_URL).text
    years = [int(y) for y in re.findall(r'data-date="01/01/(\d{4})"', h)]
    events = h.split('class="cd-h-timeline__event text-component"')[1:]
    if len(events) != len(years):
        raise RuntimeError(f"50 Best page layout changed: {len(events)} lists vs {len(years)} years")
    rows = []
    for y, ev in zip(years, events):
        for rank, name, place in re.findall(
                r'class="rank[^"]*"\s*>(\d+)</p>.*?<h2>(.*?)</h2><p>(.*?)</p>', ev, re.S):
            if "New York" in place or "Brooklyn" in place:
                rows.append({"name": re.sub(r"&#39;|&amp;", lambda m: {"&#39;": "'", "&amp;": "&"}[m.group(0)], name),
                             "person": None, "year": y, "list": "worlds_50_best",
                             "award": "ranks 1-50" if int(rank) <= 50 else "ranks 51-100",
                             "rating": rank, "borough": "Brooklyn" if "Brooklyn" in place else "Manhattan",
                             "raw": place})
    print(f"50 Best: lists for {years[0]}-{years[-1]} ({len(years)} years)")
    return pd.DataFrame(rows)


def run() -> pd.DataFrame:
    df = pd.concat([jbf(), w50()], ignore_index=True)
    c = rc.connect()
    keys = df[["name", "borough"]].drop_duplicates().reset_index(drop=True)
    keys["rid"] = keys.index
    first = df.groupby(["name", "borough"], dropna=False).year.min().rename("year").reset_index()
    keys = keys.merge(first, on=["name", "borough"], how="left")
    m = rc.match_name(c, keys, "rid", boro_col="borough")
    keys = keys.drop(columns="year").merge(m, on="rid", how="left").drop(columns="rid")
    df = df.merge(keys, on=["name", "borough"], how="left")
    rc.write(df, "awards_nyc")
    for lst, g in df.groupby("list"):
        u = g.drop_duplicates(["name", "borough"])
        print(f"{lst}: {len(g)} rows, {len(u)} venues, {g.year.min()}-{g.year.max()}, "
              f"CAMIS match {u.camis.notna().mean():.0%}")
    return df


if __name__ == "__main__":
    run()
