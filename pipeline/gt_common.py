"""Shared helpers for the ground-truth pipeline (fetch_groundtruth.py, gt_*.py).

- Two HTTP clients:
  * `get(url)`: publishers' own APIs (Blogger JSON feeds, WordPress REST), >= 1.5 s per host.
  * `ia_get(url)`: the ONE archive.org client (CDX only), >= 2.5 s between requests,
    honours Retry-After and backs off on 429/5xx. archive.org is shared with other agents.
- Text normalisation and event classification for post titles / slugs / labels.

Only metadata is stored (title, date, URL, labels, extracted names), never article text.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "groundtruth"
CACHE = OUT / "_cache"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

UA = "nyc-food-churn research script (personal, non-commercial; groundtruth; polite rate)"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA
_last_host: dict[str, float] = {}


class Gone(Exception):
    """Permanent miss (4xx other than 429): do not retry."""


def _wait(key: str, gap: float) -> None:
    w = gap - (time.time() - _last_host.get(key, 0.0))
    if w > 0:
        time.sleep(w)


def _fetch(url: str, key: str, gap: float, tries: int, params=None, timeout=90) -> requests.Response:
    last: Exception | None = None
    for i in range(tries):
        _wait(key, gap)
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            _last_host[key] = time.time()
        except requests.RequestException as e:
            _last_host[key] = time.time()
            last = e
            print(f"  network error ({e.__class__.__name__}) try {i + 1}: {url[:100]}", flush=True)
            time.sleep(10 * (i + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            ra = r.headers.get("Retry-After", "")
            wait = int(ra) if ra.isdigit() else min(20 * 2 ** i, 600)
            print(f"  HTTP {r.status_code} -> sleep {wait}s (Retry-After={ra or '-'}): {url[:100]}",
                  flush=True)
            last = RuntimeError(f"HTTP {r.status_code}")
            time.sleep(wait)
            continue
        raise Gone(f"HTTP {r.status_code} for {url}")
    raise RuntimeError(f"GET failed after {tries} tries: {url}") from last


def get(url: str, params=None, gap: float = 1.5, tries: int = 5) -> requests.Response:
    return _fetch(url, urlparse(url).netloc, gap, tries, params)


def ia_get(url: str, params=None, tries: int = 7) -> requests.Response:
    """The single archive.org client: >= 2.5 s between requests, Retry-After / backoff."""
    return _fetch(url, "archive.org", 2.5, tries, params, timeout=180)


def cached_json(name: str, fn):
    """Run fn() once and cache its JSON-able result under _cache/<name>.json."""
    p = CACHE / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    res = fn()
    p.write_text(json.dumps(res))
    return res


# ---------- text ----------
def norm(s) -> str:
    """Upper-case ASCII words: accents stripped, & -> AND, apostrophes dropped, rest -> space."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.upper().replace("&AMP;", "&").replace("&#8217;", "").replace("&#039;", "")
    s = re.sub(r"&#\d+;", " ", s).replace("&", " AND ")
    s = re.sub(r"[’'`´]", "", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def mnorm(s) -> str:
    """norm() for name matching: also drops the word AND ("Picnic Market & Cafe" = "PICNIC MARKET CAFE")."""
    return " ".join(t for t in norm(s).split() if t != "AND")


EVENT_RE = [  # first match wins (order = priority)
    ("notclose", r"\bBUT (IT ?S|IS) NOT\b|\bNOT (CLOSING|CLOSED|SHUTTERING|GOING ANYWHERE)\b|\bWON ?T CLOSE\b|\bISN ?T CLOSING\b|\bNO PLANS TO CLOSE\b|\bRUMORS?\b"),
    ("reopen", r"\bRE ?OPEN\w*|\bBACK OPEN\b|\bIS BACK\b|\bRETURNS?\b|\bRETURNING\b|\bRESURRECT|\bREBORN\b|\bREVIV"),
    ("relocate", r"\bRELOCAT|\bMOVING (TO|ACROSS|DOWN|UP|AROUND)\b|\bMOVES (TO|ACROSS|DOWN|UP|AROUND)\b|\bMOVED (TO|ACROSS)\b|\bNEW (LOCATION|HOME|SPACE|DIGS)\b"),
    ("temp", r"\bTEMPORAR|\bCLOS(ED|ES|ING) FOR (?!GOOD\b)|\bSHUT DOWN BY\b|\bSHUTTERED BY\b|\bDEPT OF\b|\bDEPARTMENT OF\b|\bSLA\b|\bNYPD\b|\bPADLOCK|\b(STILL|REMAINS?) (CLOSED|SHUTTERED|DARK)\b|\bCURRENTLY (CLOSED|SHUTTERED)\b|\bCLOSED (UNTIL|AFTER|DUE|BY|FOLLOWING|FOR NOW)\b|\bFIRE\b|\bFLOOD|\bSANDY\b|\bGAS (LEAK|OUTAGE|SHUT)|\bNO GAS\b|\bCLOSED SINCE\b|\bCLOSED FOR (RENOVATION|REPAIR|VACATION|THE|A |SUMMER|WINTER|AUGUST|PRIVATE)|\bHEALTH (DEPT|DEPARTMENT)\b|\bDOH\b|\bDOHMH\b|\bSHUT(TERED)? BY\b|\bSEIZED\b|\bSTOP WORK\b|\bPOP ?UP\b"),
    ("close", r"\bCLOS(ED|ES|ING|URE|URES)\b|\bSHUTTER|\bSHUTS?\b|\bSHUT DOWN\b|\bRIP\b|\bR I P\b|\bLAST (DAY|CALL|SERVICE|WEEKEND|DAYS|SUPPER)\b|\bLAST NIGHT (FOR|AT|OF)\b|\bFINAL (DAY|NIGHT|DAYS|WEEKEND)\b|\bOUT OF BUSINESS\b|\bCALLS? IT QUITS\b|\bGOING OUT\b|\bDARK(ENED)?\b|\bNO MORE\b|\bVANISH|\bGONE\b(?! WILD)|\bFAREWELL\b|\bGOODBYE\b|\bBIDS ADIEU\b|\bDEMISE\b|\bEND OF AN ERA\b|\bEVICT|\bFOLD(S|ED)\b|\bKAPUT\b|\bDONE FOR\b|\bLOST\b|\bSAYS? GOODBYE\b|\bSHUTTERED\b"),
    ("for_rent", r"\bFOR (RENT|LEASE)\b|\bAVAILABLE\b|\bVACANT\b|\bEMPTY\b|\bFORMER\b"),
    ("open", r"\bNOW OPEN\b|\bOPEN NOW\b|\bIS OPEN\b|\bOPEN FOR BUSINESS\b|\bOPEN(S|ED)\b|\bGRAND OPENING\b|\bDEBUT|\bFIRST LOOK\b|\bSOFT OPEN|\bGRAND OPENING\b|\bNOW SERVING\b|\bARRIVES?\b|\bLAUNCH(ES|ED)?\b|\bUNVEIL"),
]
_EVENT_RE = [(k, re.compile(p)) for k, p in EVENT_RE]
MONTHS = "JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|SPRING|SUMMER|FALL|AUTUMN|WINTER"
COMING_RE = re.compile(r"\bCOMING (SOON|TO)\b|(?<!GRAND )\bOPENING\b(?! DAY)|\bOPENS? (THIS|NEXT|LATER|EARLY|LATE) |\bOPENS? IN (A|TWO|THREE|\d+|THE COMING|LATE|EARLY)\b|"
                       rf"\bOPENS? (IN )?({MONTHS})\b|\bBRING(S|ING)\b|\bGIVING WAY\b|\bTAKING SHAPE\b|\bNOT BEEN OPEN\b|"
                       r"\bHASN ?T OPENED\b|\bYET TO OPEN\b|\bARRIVING\b|\bSOON\b|\bSET TO\b|\bNOT OPEN\b|\bWILL OPEN\b|\bTO OPEN\b|\bOPENING (SOON|THIS|NEXT|IN|LATER)\b|\bPLANS?\b|\bHEADED\b|\bHEADING\b|\bIN THE WORKS\b|\bSIGNS? (UP|GO)\b|\bLEASE\b|\bTAKING OVER\b|\bREPLAC")


def classify(text: str) -> str | None:
    """Event in a normalised title/slug: reopen / relocate / temp / close / open / coming / None."""
    t = norm(text)
    for k, rx in _EVENT_RE:
        if rx.search(t):
            if k == "open" and COMING_RE.search(t):
                return "coming"
            return k
    if COMING_RE.search(t):
        return "coming"
    return None


def save(df: pd.DataFrame, name: str) -> Path:
    p = OUT / f"{name}.parquet"
    df.to_parquet(p, index=False)
    print(f"wrote {p.relative_to(ROOT)}: {len(df):,} rows", flush=True)
    return p
