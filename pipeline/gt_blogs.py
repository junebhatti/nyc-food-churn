"""Neighbourhood blogs via their own public feeds/APIs (robots.txt checked 2026-10-18).

- Blogger JSON feeds (EV Grieve, Jeremiah's Vanishing New York): every post's title,
  published date, URL and labels. `feeds/posts/summary` is used; the summary text is dropped.
- WordPress REST API (West Side Rag, Tribeca Citizen, Greenpointers): posts in the food /
  open-closed categories: title, date, URL, tag names.

Skipped because robots.txt disallows Claude / AI agents: ny.eater.com, grubstreet.com,
brownstoner.com, Queens Post sites (Sunnyside/Astoria/LIC/Jackson Heights Post). Eater and
Grub Street are covered by URL slugs from the Wayback CDX index instead (gt_wayback.py).

Output: posts_blogs.parquet with source, post_id, date, title, url, labels (list), area.
"""
from __future__ import annotations

import html

import pandas as pd

from gt_common import cached_json, get, save

BLOGGER = {  # source -> (base URL, area code used for location matching)
    "evgrieve": ("https://evgrieve.com", "ev"),
    "vanishingny": ("https://vanishingnewyork.blogspot.com", "nyc"),
}
WORDPRESS = {  # source -> (base URL, {"categories"/"tags": ids}, area)
    "westsiderag": ("https://www.westsiderag.com", {"categories": [75, 8]}, "uws"),
    "tribecacitizen": ("https://www.tribecacitizen.com", {"categories": [9]}, "tribeca"),
    "greenpointers": ("https://greenpointers.com", {"categories": [68, 15342]}, "greenpoint"),
}


def blogger(src: str) -> pd.DataFrame:
    base, area = BLOGGER[src]
    rows, start = [], 1
    while True:
        def page(start=start):
            r = get(f"{base}/feeds/posts/summary", params={
                "alt": "json", "max-results": 150, "start-index": start, "orderby": "published"})
            f = r.json()["feed"]
            out = []
            for e in f.get("entry", []):
                link = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), None)
                out.append({"post_id": e["id"]["$t"], "date": e["published"]["$t"][:10],
                            "title": e["title"]["$t"], "url": link,
                            "labels": [c["term"] for c in e.get("category", [])]})
            return out
        got = cached_json(f"blogger_{src}_{start}", page)
        rows += got
        if start % 3000 == 1:
            print(f"  {src}: {len(rows):,} posts (latest page date {got[-1]['date'] if got else '-'})",
                  flush=True)
        if len(got) < 150:
            break
        start += 150
    df = pd.DataFrame(rows).drop_duplicates("post_id")
    df["source"], df["area"] = src, area
    return df


def wp_tag_names(base: str, ids: set[int], key: str) -> dict[int, str]:
    ids = sorted(ids)
    out: dict[int, str] = {}
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        res = cached_json(f"wp_{key}_tags_{i}", lambda chunk=chunk: get(
            f"{base}/wp-json/wp/v2/tags",
            params={"include": ",".join(map(str, chunk)), "per_page": 100,
                    "_fields": "id,name"}).json())
        out.update({t["id"]: html.unescape(t["name"]) for t in res})
    return out


def wordpress(src: str) -> pd.DataFrame:
    base, filt, area = WORDPRESS[src]
    rows = []
    for kind, ids in filt.items():
        for cid in ids:
            p = 1
            while True:
                def page(p=p, cid=cid):
                    r = get(f"{base}/wp-json/wp/v2/posts", params={
                        kind: cid, "per_page": 100, "page": p, "orderby": "date", "order": "asc",
                        "_fields": "id,date,link,title,tags"})
                    return {"total_pages": int(r.headers.get("X-WP-TotalPages", "1")), "posts": r.json()}
                got = cached_json(f"wp_{src}_{kind}{cid}_{p}", page)
                rows += got["posts"]
                if p >= got["total_pages"]:
                    break
                p += 1
            print(f"  {src} {kind} {cid}: {len(rows):,} posts so far", flush=True)
    df = pd.DataFrame(rows).drop_duplicates("id")
    names = wp_tag_names(base, {t for ts in df["tags"] for t in ts}, src)
    return pd.DataFrame({
        "source": src, "post_id": df["id"].astype(str), "date": df["date"].str[:10],
        "title": [html.unescape(t["rendered"]) for t in df["title"]], "url": df["link"],
        "labels": [[names.get(t, "") for t in ts] for ts in df["tags"]], "area": area})


def run() -> pd.DataFrame:
    parts = []
    for s in BLOGGER:
        parts.append(blogger(s))
        print(f"{s}: {len(parts[-1]):,} posts", flush=True)
    for s in WORDPRESS:
        parts.append(wordpress(s))
        print(f"{s}: {len(parts[-1]):,} posts", flush=True)
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["date_precision"] = "day"
    save(df, "posts_blogs")
    return df


if __name__ == "__main__":
    run()
