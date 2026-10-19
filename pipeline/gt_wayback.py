"""Eater NY and Grub Street post URLs from the Wayback CDX index (URL metadata only).

ny.eater.com and grubstreet.com disallow Claude / AI agents in robots.txt, so neither site
nor their archived pages are fetched. The CDX index (archive.org's own URL list) gives each
post URL and its first capture; the URL carries the post date and a slug made from the
headline, e.g.
    ny.eater.com/archives/2012/03/shutter_alert_xyz.php      (2005-2014, month precision)
    ny.eater.com/2016/3/14/11223344/xyz-closing-east-village   (2014-,   day precision)
    nymag.com/daily/food/2012/03/xyz-closes.html              (month precision)
    www.grubstreet.com/2019/05/xyz-closing.html               (month precision)

Pages are fetched one at a time through gt_common.ia_get (the single archive.org client).
Output: posts_wayback.parquet (source, post_id, date, date_precision, title=slug words, url).
"""
from __future__ import annotations

import re
import time
import sys

import pandas as pd

from gt_common import CACHE, Gone, ia_get, save

CDX = "https://web.archive.org/cdx/search/cdx"
PREFIXES = {  # source -> CDX url prefixes
    "eater": ["ny.eater.com/archives/", "ny.eater.com/20"],
    "grubstreet": ["nymag.com/daily/food/", "www.grubstreet.com/20"],
}
KEEP = re.compile(r"clos|shut|open|rip[-_]|[-_]rip|r-i-p|last[-_](day|night|call|service|weekend)|final[-_]|"
                  r"reloc|moving|moves|farewell|goodbye|quits|demise|darken|dead|gone|debut|first[-_]look|"
                  r"return|reviv|evict|vanish|no[-_]more|bids[-_]adieu|kaput|folds|done[-_]for", re.I)
PAT = [  # (regex on the original URL, precision)
    (re.compile(r"ny\.eater\.com/(\d{4})/(\d{1,2})/(\d{1,2})/\d+/([a-z0-9-]+)"), "day"),
    (re.compile(r"ny\.eater\.com/archives/(\d{4})/(\d{2})/([a-z0-9_-]+)\.php"), "month"),
    (re.compile(r"nymag\.com/daily/food/(\d{4})/(\d{2})/([a-z0-9_-]+)\.html"), "month"),
    (re.compile(r"grubstreet\.com/(\d{4})/(\d{2})/([a-z0-9_-]+)\.html"), "month"),
]


def cdx_page(prefix: str, page: int) -> list[str]:
    """Matching 'original timestamp' lines of one CDX page (cached, relevant lines only)."""
    p = CACHE / "cdx" / f"{prefix.replace('/', '_')}_{page}.txt"
    if p.exists():
        return p.read_text().splitlines()
    for attempt in range(4):
        r = ia_get(CDX, params={"url": prefix, "matchType": "prefix", "page": page,
                                "fl": "original,timestamp,statuscode", "collapse": "urlkey"})
        if "<html" not in r.text[:500].lower():
            break
        print(f"  CDX answered with an HTML page (archive.org offline?); sleep 300s", flush=True)
        time.sleep(300)
    else:
        raise RuntimeError(f"CDX kept returning HTML for {prefix} page {page}")
    keep = [ln for ln in r.text.splitlines() if KEEP.search(ln.split(" ")[0])]
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(keep))
    return keep


def num_pages(prefix: str) -> int:
    r = ia_get(CDX, params={"url": prefix, "matchType": "prefix", "showNumPages": "true"})
    return int(r.text.strip())


def parse(source: str, lines: list[str]) -> pd.DataFrame:
    rows = []
    for ln in lines:
        parts = ln.split(" ")
        if len(parts) < 2:
            continue
        url, ts = parts[0], parts[1]
        for rx, prec in PAT:
            m = rx.search(url)
            if not m:
                continue
            g = m.groups()
            y, mo = int(g[0]), int(g[1])
            slug = g[-1]
            if prec == "day":
                d = pd.Timestamp(y, mo, int(g[2]))
            else:  # month only: first capture if it falls in that month, else mid-month
                cap = pd.Timestamp(ts[:8])
                d = cap if (cap.year, cap.month) == (y, mo) else pd.Timestamp(y, mo, 15)
            rows.append({"source": source, "post_id": f"{y}/{mo}/{slug}", "date": d,
                         "date_precision": prec, "first_capture": pd.Timestamp(ts[:8]),
                         "title": re.sub(r"[-_]+", " ", slug), "url": url.split("?")[0]})
            break
    df = pd.DataFrame(rows)
    return df.sort_values("first_capture").drop_duplicates("post_id") if len(df) else df


def cached_lines(prefix: str) -> tuple[list[str], int]:
    files = sorted((CACHE / "cdx").glob(f"{prefix.replace('/', '_')}_*.txt"))
    return [ln for f in files for ln in f.read_text().splitlines()], len(files)


def run(offline: bool = False) -> pd.DataFrame:
    """offline=True: parse only the CDX pages already cached (no network)."""
    out, failed = [], []
    for source, prefixes in PREFIXES.items():
        lines = []
        for prefix in prefixes:
            if offline:
                got, n = cached_lines(prefix)
                lines += got
                print(f"{source} {prefix}: {n} cached CDX pages", flush=True)
                continue
            n = num_pages(prefix)
            print(f"{source} {prefix}: {n} CDX pages", flush=True)
            for page in range(n):
                try:
                    lines += cdx_page(prefix, page)
                except (RuntimeError, Gone) as e:
                    print(f"  page {page} FAILED: {e}", flush=True)
                    failed.append((prefix, page))
                if page % 10 == 0:
                    print(f"  {prefix} page {page}/{n}: {len(lines):,} candidate lines", flush=True)
        out.append(parse(source, lines))
        print(f"{source}: {len(out[-1]):,} candidate posts", flush=True)
    if failed:
        print(f"{len(failed)} CDX pages failed; rerun to retry them (cached pages are skipped): {failed}",
              file=sys.stderr)
    df = pd.concat(out, ignore_index=True)
    save(df, "posts_wayback")
    return df


if __name__ == "__main__":
    run(offline="--offline" in sys.argv)
