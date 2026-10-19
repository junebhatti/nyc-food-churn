"""One polite archive.org client for the early-history (pre-2012-07) search.

archive.org is shared with other agents: every request goes through IA.get(),
which keeps >= 3 s between requests and backs off on 429/503 (honouring Retry-After).
"""
from __future__ import annotations

import sys
import time

import requests

UA = {"User-Agent": "nyc-food-churn research (early DOHMH history)"}
MIN_GAP = 3.5


class IA:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.last = 0.0

    def get(self, url: str, params: dict | None = None, stream: bool = False,
            allow_redirects: bool = True, tries: int = 6) -> requests.Response:
        for attempt in range(tries):
            wait = self.last + MIN_GAP - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                r = self.s.get(url, params=params, stream=stream, timeout=(30, 300),
                               allow_redirects=allow_redirects)
            except requests.RequestException as e:
                print(f"  IA {url}: {e} (attempt {attempt + 1})", file=sys.stderr)
                time.sleep(15 * (attempt + 1))
                continue
            if r.status_code in (429, 503, 502, 504):
                ra = r.headers.get("Retry-After")
                delay = int(ra) if ra and ra.isdigit() else 20 * (attempt + 1)
                print(f"  IA {r.status_code} on {url}; sleeping {delay}s", file=sys.stderr)
                r.close()
                time.sleep(delay)
                continue
            return r
        raise RuntimeError(f"archive.org kept failing for {url}")

    def cdx(self, url: str, match: str = "prefix", **kw) -> list[list[str]]:
        params = {"url": url, "matchType": match, "output": "json",
                  "fl": "timestamp,original,statuscode,mimetype,length,digest", **kw}
        r = self.get("https://web.archive.org/cdx/search/cdx", params=params)
        if r.status_code != 200:
            raise RuntimeError(f"CDX {url}: HTTP {r.status_code} {r.text[:200]}")
        rows = r.json() if r.text.strip() else []
        return rows[1:]


if __name__ == "__main__":
    ia = IA()
    for u in sys.argv[1:]:
        for row in ia.cdx(u, collapse="urlkey", limit="5000"):
            print(*row)
