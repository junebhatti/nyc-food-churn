"""Eater NY Essential 38 and Heatmaps over time, from Wayback Machine captures.

One capture per list per quarter (2015 -> now). Three page layouts are parsed:
  2015-17  data-coordinates="lon, lat" data-name="..."
  2017-25  map JSON points (title first, or title:null ... title last in late 2024): "slug":..,"title":"..","id":n,"lat":..,"lon":..
  2025-26  Next.js JSON: "location":{"latitude":..,"longitude":..},"name":".."
Output: eater_lists.parquet  (list, snapshot date, name, lat, lon, position, camis)
"""
from __future__ import annotations

import html
import re

import pandas as pd

import ratings_common as rc

LISTS = {
    "eater_38": ["ny.eater.com/maps/best-new-york-restaurants-38",
                 "ny.eater.com/maps/best-new-york-restaurants-38-2",
                 "ny.eater.com/maps/best-new-york-restaurants-38-map"],
    "eater_heatmap_nyc": ["ny.eater.com/maps/best-new-nyc-restaurants-heatmap"],
    "eater_heatmap_brooklyn": ["ny.eater.com/maps/best-new-brooklyn-restaurants-heatmap",
                               "ny.eater.com/maps/best-new-restaurants-brooklyn-heatmap"],
    "eater_heatmap_queens": ["ny.eater.com/maps/best-new-queens-restaurants-heatmap"],
}
CDX = "https://web.archive.org/cdx/search/cdx"

PAT_A = re.compile(r'data-coordinates="(-?[\d.]+),\s*(-?[\d.]+)"\s+data-name="([^"]+)"')
PAT_B = re.compile(r'"type":"point","slug":"[^"]*","title":(?:null|"((?:[^"\\]|\\.)*)"),"id":\d+,'
                   r'"lat":(-?[\d.]+),"lon":(-?[\d.]+)(?:,"title":"((?:[^"\\]|\\.)*)")?')
PAT_C = re.compile(r'"location":\{"latitude":(-?[\d.]+),"longitude":(-?[\d.]+)\},"name":"((?:[^"\\]|\\.)*)"')


def captures(url: str) -> pd.DataFrame:
    r = rc.get(CDX, params={"url": url, "filter": "statuscode:200", "fl": "timestamp,original,digest"}, delay=1.5)
    rows = [ln.split(" ") for ln in r.text.splitlines() if ln.strip()]
    return pd.DataFrame(rows, columns=["ts", "original", "digest"])


def parse(h: str) -> list[tuple[str, float, float]]:
    h = html.unescape(h)
    out = [(n, float(la), float(lo)) for lo, la, n in PAT_A.findall(h)]
    if not out:
        out = [(n or n2, float(la), float(lo)) for n, la, lo, n2 in PAT_B.findall(h) if n or n2]
    if not out:
        out = [(n, float(la), float(lo)) for la, lo, n in PAT_C.findall(h)]
    seen, res = set(), []
    for n, la, lo in out:  # pages repeat the points; keep first occurrence order
        n = n.encode().decode("unicode_escape", errors="ignore") if "\\u" in n else n
        n = n.replace('\\"', '"')
        if n not in seen:
            seen.add(n)
            res.append((n, la, lo))
    return res


def run() -> pd.DataFrame:
    rows, log = [], []
    for lst, urls in LISTS.items():
        caps = pd.concat([captures(u) for u in urls], ignore_index=True)
        if caps.empty:
            print(lst, "no captures")
            continue
        caps["q"] = caps.ts.str[:4] + "Q" + ((caps.ts.str[4:6].astype(int) - 1) // 3 + 1).astype(str)
        caps = caps.sort_values("ts").drop_duplicates("digest")
        # pick the latest capture in each quarter, and fall back to the next one if it fails to parse
        for q, g in caps.groupby("q"):
            for _, cap in g.sort_values("ts", ascending=False).head(3).iterrows():
                try:
                    h = rc.get(f"https://web.archive.org/web/{cap.ts}id_/{cap.original}", delay=1.5).text
                except Exception as e:  # log and try the next capture in this quarter
                    print(f"  {lst} {cap.ts}: fetch failed: {e}")
                    continue
                items = parse(h)
                title = re.search(r"<title>(.*?)</title>", h, re.S)
                if len(items) >= 5:
                    for pos, (n, la, lo) in enumerate(items, 1):
                        rows.append({"list": lst, "quarter": q, "snapshot": pd.to_datetime(cap.ts[:8]),
                                     "name": n, "lat": la, "lon": lo, "position": pos,
                                     "page_title": html.unescape(title.group(1).strip()) if title else None,
                                     "wayback_url": f"https://web.archive.org/web/{cap.ts}/{cap.original}"})
                    log.append((lst, q, len(items)))
                    break
                print(f"  {lst} {cap.ts}: only {len(items)} items parsed")
        print(lst, "quarters:", sum(1 for x in log if x[0] == lst))
    df = pd.DataFrame(rows)
    df = df[df.lat.between(40.4, 41.0) & df.lon.between(-74.3, -73.6)].reset_index(drop=True)
    c = rc.connect()
    places = df[["name", "lat", "lon"]].drop_duplicates(["name"]).reset_index(drop=True)
    places["pid"] = places.index
    m = rc.match_geo(c, places, "pid")
    places = places.merge(m, on="pid", how="left")[["name", "camis", "match_sim", "match_m"]]
    df = df.merge(places, on="name", how="left")
    rc.write(df, "eater_lists")
    u = df.drop_duplicates(["list", "name"])
    print(u.groupby("list").camis.agg(lambda s: f"{s.notna().mean():.0%} of {len(s)} venues matched").to_string())
    return df


if __name__ == "__main__":
    run()
