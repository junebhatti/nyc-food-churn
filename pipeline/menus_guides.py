"""Archived restaurant-guide pages with a stated price, via the Wayback Machine.

  zagat   zagat.com/r/<slug>-<city>   2011-2016 server-rendered pages: Cost ($ per person,
          dinner + drink + tip), Food/Decor/Service scores, schema.org address.
          2019+ captures are an empty client-side shell, so they are skipped.
  nymag   nymag.com/listings/restaurant/<slug>   $-$$$$ price range, hCard address, lat/lon.

    python menus_guides.py cdx <site> [start]   # CDX pages -> _wayback/<site>_cdx/
    python menus_guides.py fetch <site> [workers]  # one capture per URL, parse -> JSONL
    python menus_guides.py build                # -> guides.parquet (matched to CAMIS)
"""
from __future__ import annotations

import html as htmllib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from menus_common import OUT, Gone, get

WB = OUT / "_wayback"
CDX_API = "https://web.archive.org/cdx/search/cdx"
NYC_CITY = r"new-york|manhattan|brooklyn|queens|bronx|staten-island|long-island-city|astoria|flushing|williamsburg|harlem"
SITES = {
    "zagat": {"url": "zagat.com/r/", "years": (2011, 2016),
              "key": re.compile(rf"^com,zagat\)/r/([^/?]+-(?:{NYC_CITY}))/?$")},
    "nymag": {"url": "nymag.com/listings/restaurant/", "years": (2011, 2019),
              "key": re.compile(r"^com,nymag\)/listings/restaurant/([^/?]+)/?$")},
}
F = re.S | re.I
RX = {
    "zagat": {
        "name": r'itemprop="name">\s*([^<]+)',
        "cost": r'i-text">Cost</span><span class="i-number">\$?(\d+)',
        "food": r'i-text">Food</span><span class="i-number[^"]*" itemprop="ratingValue">(\d+)',
        "decor": r'i-text">Decor</span><span class="i-number[^"]*" itemprop="ratingValue">(\d+)',
        "service": r'i-text">Service</span><span class="i-number[^"]*" itemprop="ratingValue">(\d+)',
        "street": r'itemprop="streetAddress">([^<]+)', "zip": r'itemprop="postalCode">([^<]+)',
        "locality": r'itemprop="addressLocality">([^<]+)',
        "lat": r'itemprop="latitude" content="(-?[\d.]+)', "lon": r'itemprop="longitude" content="(-?[\d.]+)',
    },
    "nymag": {
        "name": r'property="og:title" content="([^"]+)', "price_level": r'pricerange">\s*(\$+)',
        "street": r'class="street-address">([^<]+)', "zip": r'class="postal-code">([^<]+)',
        "locality": r'class="locality">([^<]+)',
        "lat": r'class="latitude">\s*(-?[\d.]+)', "lon": r'class="longitude">\s*(-?[\d.]+)',
    },
}
RX = {s: {k: re.compile(v, F) for k, v in d.items()} for s, d in RX.items()}


def parse(site: str, h: str) -> dict:
    out = {}
    for k, rx in RX[site].items():
        m = rx.search(h)
        out[k] = re.sub(r"\s+", " ", htmllib.unescape(m.group(1))).strip() if m else None
    return out


def cdx(site: str, start: int = 0) -> None:
    d = WB / f"{site}_cdx"
    d.mkdir(parents=True, exist_ok=True)
    base = {"url": SITES[site]["url"], "matchType": "prefix"}
    n = int(get(CDX_API, params={**base, "showNumPages": "true"}).text.strip())
    print(f"{site} CDX: {n} pages", flush=True)
    for attempt in range(4):
        missing = [p for p in list(range(start, n)) + list(range(start))
                   if not (d / f"p{p:03d}.txt").exists()]
        if not missing:
            return
        for p in missing:
            if (d / f"p{p:03d}.txt").exists():
                continue
            try:
                r = get(CDX_API, timeout=600, tries=3, params={
                    **base, "filter": "statuscode:200", "fl": "urlkey,timestamp,original", "page": p})
            except RuntimeError as e:
                print(f"  page {p} FAILED this pass: {e}", flush=True)
                continue
            if "<html" in r.text[:200].lower():
                print(f"  page {p} returned HTML: {r.text[:100]!r}", flush=True)
                continue
            (d / f"p{p:03d}.txt").write_text(r.text)
            print(f"  page {p}: {r.text.count(chr(10)):,} lines", flush=True)
            time.sleep(1)
    print(f"{site} CDX incomplete; rerun", flush=True)


def select(site: str) -> pd.DataFrame:
    cfg, rows = SITES[site], []
    for f in sorted((WB / f"{site}_cdx").glob("p*.txt")):
        for line in f.read_text().splitlines():
            parts = line.split(" ")
            m = cfg["key"].match(parts[0]) if len(parts) >= 3 else None
            if m:
                rows.append((m.group(1), parts[1], parts[2]))
    df = pd.DataFrame(rows, columns=["slug", "ts", "original"])
    y = df.ts.str[:4].astype(int)
    df = df[y.between(*cfg["years"])]
    df = df.sort_values("ts").groupby("slug").tail(1)  # latest capture in the window
    print(f"{site}: {len(df):,} slugs with a capture in {cfg['years']}", flush=True)
    return df


_lock = threading.Lock()


def fetch(site: str, workers: int = 2) -> None:
    out, bad = WB / f"{site}_parsed.jsonl", WB / f"{site}_failed.jsonl"
    done = set()
    for f in (out, bad):
        if f.exists():
            done.update(json.loads(l)["slug"] for l in open(f) if l.strip())
    todo = select(site)
    todo = todo[~todo.slug.isin(done)]
    print(f"{site} fetch: {len(done):,} done, {len(todo):,} to go", flush=True)

    def one(row):
        try:
            h = get(f"https://web.archive.org/web/{row.ts}id_/{row.original}", timeout=90, tries=5)
            rec, f = parse(site, h.content.decode("utf-8", "replace")), out
            rec.update(slug=row.slug, ts=row.ts, url=row.original)
        except (Gone, RuntimeError) as e:
            rec, f = {"slug": row.slug, "ts": row.ts, "err": str(e)[:200]}, bad
        with _lock, open(f, "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(one, todo.itertuples(index=False)), 1):
            if i % 200 == 0:
                print(f"  {i:,}/{len(todo):,} {i / (time.time() - t0):.2f}/s", flush=True)


def build() -> pd.DataFrame:
    from menus_match import match
    frames = []
    for site in SITES:
        p = WB / f"{site}_parsed.jsonl"
        if p.exists():
            frames.append(pd.DataFrame([json.loads(l) for l in open(p)]).assign(source=f"{site}_wayback"))
    df = pd.concat(frames, ignore_index=True)
    for c in ("cost", "food", "decor", "service", "lat", "lon"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["snapshot_date"] = pd.to_datetime(df.ts.str[:8], format="%Y%m%d")
    df["price_level_n"] = df.price_level.str.len()
    df["id"] = df.source + ":" + df.slug
    nyc = df.zip.fillna("").str.match(r"^1(0[0-4]|1[0-6])\d\d")
    print(f"guides parsed {len(df):,}; NYC zip {nyc.sum():,}; with cost {df.cost.notna().sum():,}; "
          f"with $ level {df.price_level.notna().sum():,}")
    df = df[nyc].copy()
    parts = df.street.fillna("").str.extract(r"^\s*([0-9][0-9A-Za-z/ -]*?)\s+(.*)$")
    src = pd.DataFrame({"id": df.id, "name": df.name, "house": parts[0], "street": parts[1],
                        "zip": df.zip, "lat": df.lat, "lon": df.lon, "year": df.snapshot_date.dt.year})
    df = df.merge(match(src), on="id", how="left")
    for s, g in df.groupby("source"):
        print(f"  {s}: {len(g):,} rows, matched {g.camis.notna().mean():.1%}")
    cols = ["source", "slug", "name", "street", "locality", "zip", "lat", "lon", "snapshot_date",
            "price_level", "price_level_n", "cost", "food", "decor", "service", "url",
            "camis", "match_method", "match_sim", "n_candidates"]
    df = df.reindex(columns=cols)
    df.to_parquet(OUT / "guides.parquet", index=False)
    print(f"wrote guides.parquet ({len(df):,})")
    return df


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "cdx":
        cdx(args[0], int(args[1]) if len(args) > 1 else 0)
    elif cmd == "fetch":
        fetch(args[0], int(args[1]) if len(args) > 1 else 2)
    elif cmd == "build":
        build()
