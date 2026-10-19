"""MenuPages.com (NYC, www.menupages.com/restaurants/<slug>/[menu]) via the Wayback Machine.

Other MenuPages cities lived on subdomains (sanfrancisco.menupages.com ...), so the
www/bare host under /restaurants/ is New York only.

Steps (resumable; each writes under data/raw/menus/_wayback/):
  cdx     page through the CDX index (status 200) -> cdx/pNNN.txt
  select  one capture per slug: latest /menu capture 2011-2019, else latest main page
  fetch   download the chosen captures sequentially (few workers), parse, append JSONL
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from menus_common import OUT, Gone, get, read_done, stats_line
from menus_parse import parse_page

WB = OUT / "_wayback"
CDX_DIR = WB / "cdx"
PARSED = WB / "menupages_parsed.jsonl"
FAILED = WB / "menupages_failed.jsonl"
CDX_API = "https://web.archive.org/cdx/search/cdx"
SLUG_RE = re.compile(r"^com,menupages\)/restaurants/([^/?]+)(/menu)?/?$")


def cdx(start: int = 0) -> None:
    """start: page to begin at (lets 2-3 polite workers split the index)."""
    CDX_DIR.mkdir(parents=True, exist_ok=True)
    base = {"url": "menupages.com/restaurants/", "matchType": "prefix"}
    n = int(get(CDX_API, params={**base, "showNumPages": "true"}).text.strip())
    print(f"CDX: {n} pages", flush=True)
    for attempt in range(8):  # passes; a page that keeps failing is retried next pass
        order = list(range(start, n)) + list(range(start))
        missing = [p for p in order if not (CDX_DIR / f"p{p:03d}.txt").exists()]
        if not missing:
            break
        print(f"pass {attempt}: {len(missing)} pages to fetch", flush=True)
        for p in missing:
            if (CDX_DIR / f"p{p:03d}.txt").exists():  # another worker got it
                continue
            try:
                r = get(CDX_API, timeout=600, tries=5,
                        params={**base, "filter": "statuscode:200",
                                "fl": "urlkey,timestamp,original,length", "page": p})
            except RuntimeError as e:
                print(f"  page {p} FAILED this pass: {e}", flush=True)
                continue
            if "<html" in r.text[:200].lower():
                print(f"  page {p} returned HTML, not index lines: {r.text[:120]!r}", flush=True)
                continue
            (CDX_DIR / f"p{p:03d}.txt").write_text(r.text)
            print(f"  page {p}: {r.text.count(chr(10)):,} lines", flush=True)
            time.sleep(1)
    left = [p for p in range(n) if not (CDX_DIR / f"p{p:03d}.txt").exists()]
    if left:
        print(f"CDX incomplete: pages {left} still missing; rerun `cdx`", flush=True)


def load_cdx() -> pd.DataFrame:
    rows = []
    for f in sorted(CDX_DIR.glob("p*.txt")):
        for line in f.read_text().splitlines():
            parts = line.split(" ")
            if len(parts) < 4:
                continue
            m = SLUG_RE.match(parts[0])
            if not m:
                continue
            rows.append((m.group(1), bool(m.group(2)), parts[1], parts[2], parts[3]))
    df = pd.DataFrame(rows, columns=["slug", "is_menu", "ts", "original", "length"])
    df["year"] = df["ts"].str[:4].astype(int)
    return df


def select() -> pd.DataFrame:
    df = load_cdx()
    print(f"CDX rows {len(df):,}; slugs {df.slug.nunique():,}; "
          f"slugs with /menu {df[df.is_menu].slug.nunique():,}")
    print(df.groupby("year").slug.nunique().to_string())
    # rank: menu page in study window > menu page any year > main page in window > main page
    inwin = df.year.between(2011, 2019)
    df["rank"] = df.is_menu.astype(int) * 2 + inwin.astype(int)
    df = df.sort_values(["slug", "rank", "ts"]).groupby("slug").tail(1)
    df = df.sort_values(["rank", "ts"], ascending=[False, False])
    df.to_csv(WB / "selected.csv", index=False)
    print(f"selected {len(df):,} captures; by rank:\n{df['rank'].value_counts().to_string()}")
    return df


_lock = threading.Lock()


def _fetch_one(row) -> None:
    url = f"https://web.archive.org/web/{row.ts}id_/{row.original}"
    try:
        html = get(url, timeout=90, tries=5).content.decode("utf-8", "replace")
        rec = parse_page(html)
        rec.update(slug=row.slug, ts=row.ts, is_menu=bool(row.is_menu), url=row.original)
        out, line = PARSED, json.dumps(rec)
    except (Gone, RuntimeError) as e:
        out, line = FAILED, json.dumps({"slug": row.slug, "ts": row.ts, "err": str(e)[:200]})
    with _lock, open(out, "a") as fh:
        fh.write(line + "\n")


def done_slugs() -> set[str]:
    return read_done(PARSED, FAILED)


def fetch(limit: int | None = None, workers: int = 3) -> None:
    sel = pd.read_csv(WB / "selected.csv", dtype=str)
    done = done_slugs()
    todo = sel[~sel.slug.isin(done)]
    if limit:
        todo = todo.head(limit)
    print(f"fetch: {len(done):,} done, {len(todo):,} to go, {workers} workers", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, _ in enumerate(ex.map(_fetch_one, todo.itertuples(index=False)), 1):
            if i % 200 == 0:
                print(f"  {i:,}/{len(todo):,}  {i / (time.time() - t0):.2f}/s {stats_line()}",
                      flush=True)


def load_parsed() -> list[dict]:
    with open(PARSED) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def archive_jsonl() -> None:
    """Compress the parsed JSONL (kept as the raw record of what was fetched)."""
    with open(PARSED, "rb") as src, gzip.open(str(PARSED) + ".gz", "wb") as dst:
        dst.write(src.read())


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "cdx":
        cdx()
    elif cmd == "select":
        select()
    elif cmd == "fetch":
        fetch(int(sys.argv[2]) if len(sys.argv) > 2 else None,
              int(sys.argv[3]) if len(sys.argv) > 3 else 3)
