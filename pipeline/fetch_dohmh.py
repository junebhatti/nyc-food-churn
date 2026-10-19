"""Download every historical copy of the DOHMH restaurant inspection dataset listed
in data/raw/dohmh/manifest.csv into data/raw/dohmh/<id>.csv.gz.

Idempotent: a copy whose output file already exists is skipped. Each copy is
stored as one gzipped CSV (original bytes for CSV sources; zip/bz2 members are
extracted; Socrata rows.xml exports are converted to CSV with their field tags
as headers). Downloads are sequential with retry/backoff and a pause between
requests to be polite to archive.org.

Manifest fetch columns: id, kind (wayback|http), url, member (regex for the file
inside a zip/tarball; blank otherwise), format (csv|xml|webextract|rda).
Run: .venv/bin/python pipeline/fetch_dohmh.py [id ...]
Then: .venv/bin/python pipeline/dohmh_profile.py  (fills the stats columns)
"""
from __future__ import annotations

import bz2
import csv
import gzip
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from xml.etree.ElementTree import iterparse

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/dohmh"
MANIFEST = RAW / "manifest.csv"
TMP = RAW / "_tmp"
PAUSE_S = 4
UA = {"User-Agent": "nyc-food-churn research (personal project; polite sequential fetch)"}


def wayback_urls(ts: str, original: str) -> list[str]:
    """Raw-playback URLs to try. Some https id_ captures 302-loop between
    neighbouring captures; the http:// spelling or plain replay usually works
    (CSV/XML bodies are not rewritten by plain replay)."""
    http = re.sub(r"^https://", "http://", original)
    return [f"https://web.archive.org/web/{ts}id_/{http}",
            f"https://web.archive.org/web/{ts}id_/{original}",
            f"https://web.archive.org/web/{ts}/{original}"]


def download(url: str, dest: Path) -> None:
    for attempt in range(5):
        try:
            with requests.get(url, stream=True, timeout=(30, 300), headers=UA,
                              allow_redirects=True) as r:
                if r.history and "web.archive.org" in url:
                    # Wayback redirected to a *different* capture; reject it.
                    ts = re.search(r"/web/(\d{14})", url).group(1)
                    if ts not in r.url:
                        raise ValueError(f"wayback redirected to other capture {r.url}")
                r.raise_for_status()
                expected = r.headers.get("content-length")
                n = 0
                with dest.open("wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                        n += len(chunk)
                if expected and r.headers.get("content-encoding") is None and int(expected) != n:
                    raise IOError(f"short read {n} of {expected} bytes")
                return
        except ValueError:
            raise
        except (requests.RequestException, IOError) as e:
            wait = 15 * (attempt + 1)
            print(f"  fetch failed ({e}); retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def looks_like_data(path: Path) -> bool:
    with path.open("rb") as fh:
        head = fh.read(4096)
    if head[:2] == b"PK" or head[:3] == b"BZh":
        return True
    low = head.lower().lstrip(b"\xef\xbb\xbf")
    return not (low.startswith(b"<!doctype html") or low.startswith(b"<html"))


def xml_to_csv(src: Path, dst_gz: Path) -> None:
    """Stream Socrata rows.xml (<response><row><row ...><field>v</field>...)."""
    cols: list[str] = []
    rows: list[dict] = []
    depth = 0
    for ev, el in iterparse(str(src), events=("start", "end")):
        if ev == "start":
            depth += 1
            continue
        depth -= 1
        if el.tag == "row" and depth == 2:  # an individual record
            rec = {}
            for c in el:
                if len(c):  # location fields have children; keep lat/lng
                    for g in c:
                        rec[f"{c.tag}_{g.tag}"] = g.text or ""
                else:
                    rec[c.tag] = c.text or ""
            for k in rec:
                if k not in cols:
                    cols.append(k)
            rows.append(rec)
            el.clear()
    with gzip.open(dst_gz, "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def rda_to_csv(tarball: Path, member: str, dst_gz: Path) -> None:
    """CRAN package tarball -> data/<X>.rda data frame -> CSV. Needs the pure-python
    `rdata` package (pip install rdata); not in the project venv by default."""
    import tarfile
    try:
        import rdata
    except ImportError as e:
        raise RuntimeError("format 'rda' needs `pip install rdata`") from e
    with tarfile.open(tarball) as t:
        m = next(x for x in t.getmembers() if re.search(member, x.name))
        (TMP / "data.rda").write_bytes(t.extractfile(m).read())
    objs = rdata.read_rda(str(TMP / "data.rda"))
    df = next(iter(objs.values()))
    for c in ("inspection_date", "grade_date", "record_date"):
        if c in df:  # POSIXct seconds since epoch (UTC)
            df[c] = (df[c].astype("float64") * 1e9).astype("datetime64[ns]").dt.strftime("%Y-%m-%d")
    df.to_csv(dst_gz, index=False, compression="gzip")


def materialize(raw: Path, member: str, fmt: str, out_gz: Path) -> None:
    src = raw
    if fmt == "rda":
        part = out_gz.with_suffix(".part")
        rda_to_csv(raw, member, part)
        part.rename(out_gz)
        return
    if raw.open("rb").read(2) == b"PK":
        with zipfile.ZipFile(raw) as z:
            names = [n for n in z.namelist() if not n.startswith("__MACOSX/")
                     and re.search(member or r"\.(csv|txt)$", n, re.I)]
            if len(names) != 1:
                raise ValueError(f"zip member regex {member!r} matched {names} in {z.namelist()}")
            src = TMP / "member"
            with z.open(names[0]) as i, src.open("wb") as o:
                shutil.copyfileobj(i, o, 1 << 20)
    elif raw.open("rb").read(3) == b"BZh":
        src = TMP / "member"
        with bz2.open(raw) as i, src.open("wb") as o:
            shutil.copyfileobj(i, o, 1 << 20)
    part = out_gz.with_suffix(".part")
    if fmt == "xml":
        xml_to_csv(src, part)
    elif fmt == "webextract":
        # old DOH WebExtract files are cp1252; store everything as UTF-8
        with src.open("r", encoding="cp1252", errors="replace", newline="") as i, \
                gzip.open(part, "wt", encoding="utf-8", newline="") as o:
            shutil.copyfileobj(i, o, 1 << 20)
    else:
        with src.open("rb") as i, gzip.open(part, "wb", compresslevel=6) as o:
            shutil.copyfileobj(i, o, 1 << 20)
    part.rename(out_gz)


def fetch_one(row: dict) -> None:
    out = RAW / f"{row['id']}.csv.gz"
    if out.exists():
        print(f"skip {row['id']} (exists)")
        return
    TMP.mkdir(exist_ok=True)
    raw = TMP / "download"
    if row["kind"] == "wayback":
        ts = row["snapshot_ts"]
        urls = wayback_urls(ts, row["url"])
    else:
        urls = [row["url"]]
    last_err = None
    for u in urls:
        print(f"get {row['id']}: {u}")
        try:
            download(u, raw)
            if not looks_like_data(raw):
                raise ValueError("got an HTML page instead of data")
            break
        except (ValueError, RuntimeError) as e:
            last_err = e
            print(f"  {e}", file=sys.stderr)
            time.sleep(PAUSE_S)
    else:
        raise RuntimeError(f"{row['id']}: all URLs failed: {last_err}")
    materialize(raw, row.get("member", ""), row["format"], out)
    for p in TMP.iterdir():
        p.unlink()
    print(f"  wrote {out.name} ({out.stat().st_size/1e6:.1f} MB)")
    time.sleep(PAUSE_S)


def main() -> None:
    with MANIFEST.open() as fh:
        rows = list(csv.DictReader(fh))
    only = set(sys.argv[1:])
    failures = []
    for row in rows:
        if only and row["id"] not in only:
            continue
        try:
            fetch_one(row)
        except Exception as e:  # keep going; report every failure at the end
            print(f"FAILED {row['id']}: {e}", file=sys.stderr)
            failures.append(row["id"])
    if failures:
        print(f"{len(failures)} failed: {failures}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
