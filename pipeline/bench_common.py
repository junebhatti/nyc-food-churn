"""Shared helpers for the official-statistics benchmark (CBP/ZBP, QCEW, BDS, BED, nonemployer)."""
import io
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "benchmarks"
# Large source zips are downloaded here and deleted after filtering.
DL = Path(os.environ.get("BENCH_DL", OUT / "_dl"))

UA = {"User-Agent": "nyc-food-churn benchmark script (python-requests)"}

NYC_COUNTIES = {"005": "Bronx", "047": "Brooklyn", "061": "Manhattan", "081": "Queens", "085": "Staten Island"}
CTY_NAME_BORO = {"BRONX": "Bronx", "KINGS": "Brooklyn", "NEW YORK": "Manhattan",
                 "QUEENS": "Queens", "RICHMOND": "Staten Island"}

# NAICS codes of interest (2012/2017/2022 vintages share these; 2007 vintage noted per year).
NAICS_KEEP = {"722", "7225", "722511", "722513", "722514", "722515", "7224", "722410",
              "311811", "445291", "4452", "722110", "722211", "722212", "722213", "72", "------"}


def log(msg):
    print(f"[bench {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def get(url, *, stream=False, tries=4, timeout=120, **kw):
    """GET with retry/backoff. Raises on final failure (never returns None silently)."""
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, stream=stream, timeout=timeout, **kw)
            if r.status_code == 404:
                r.raise_for_status()
            if r.status_code >= 400:
                raise requests.HTTPError(f"HTTP {r.status_code} for {url}")
            return r
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 404:
                raise
            last = e
        except requests.RequestException as e:
            last = e
        log(f"retry {i + 1}/{tries} {url}: {last}")
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"failed after {tries} tries: {url}: {last}")


def download(url, dest, tries=4):
    """Download to dest. census.gov's WAF sometimes answers 200 with an HTML "Request Rejected"
    page, so zip downloads are checked and retried with a long backoff."""
    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0 and (dest.suffix != ".zip" or zipfile.is_zipfile(dest)):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i in range(tries):
        with get(url, stream=True) as r, open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        if dest.suffix != ".zip" or zipfile.is_zipfile(tmp):
            break
        head = tmp.read_bytes()[:120]
        log(f"not a zip ({head!r}); retry {i + 1}/{tries} after {60 * (i + 1)} s: {url}")
        time.sleep(60 * (i + 1))
    else:
        tmp.unlink()
        raise RuntimeError(f"{url}: server kept returning a non-zip response")
    tmp.rename(dest)
    log(f"downloaded {url} ({dest.stat().st_size / 1e6:.1f} MB)")
    time.sleep(2)
    return dest


class HttpRangeFile(io.IOBase):
    """Seekable read-only file over HTTP Range requests, so zipfile can pull single members
    out of multi-hundred-MB archives (QCEW quarterly by-area zips) without downloading them."""

    def __init__(self, url):
        self.url = url
        h = requests.head(url, headers=UA, timeout=60)
        h.raise_for_status()
        if h.headers.get("Accept-Ranges") != "bytes":
            raise RuntimeError(f"server does not support ranges: {url}")
        self.size = int(h.headers["Content-Length"])
        self.pos = 0
        self._buf = (0, b"")

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        # serve from a read-ahead buffer so zipfile's many small reads don't each hit HTTP
        b0, buf = self._buf
        if not (b0 <= self.pos and self.pos + n <= b0 + len(buf)):
            end = min(self.pos + max(n, 1 << 20), self.size) - 1
            r = requests.get(self.url, headers={**UA, "Range": f"bytes={self.pos}-{end}"}, timeout=300)
            if r.status_code != 206:
                raise RuntimeError(f"range request got HTTP {r.status_code}: {self.url}")
            self._buf = (self.pos, r.content)
            b0, buf = self._buf
        out = buf[self.pos - b0:self.pos - b0 + n]
        self.pos += len(out)
        return out


def remote_zip(url):
    return zipfile.ZipFile(HttpRangeFile(url))


def zip_to_boro(z):
    """Borough from a 5-digit NYC ZIP by USPS prefix (fallback when no county name)."""
    z = str(z)[:5]
    if not (len(z) == 5 and z.isdigit()):
        return None
    p = z[:3]
    if p in {"100", "101", "102"}:
        return "Manhattan"
    if p == "103":
        return "Staten Island"
    if p == "104":
        return "Bronx"
    if p == "112":
        return "Brooklyn"
    if p in {"111", "113", "114", "116"} or z in {"11004", "11005"}:
        return "Queens"
    return None
