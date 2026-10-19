"""BID pedestrian counts that are published in machine-parseable form (text-layer PDF tables).

Sources (all automated counters, MRI OnLocation / formerly Springboard):
  - Garment District Alliance: weekly "Footfall Report" PDFs (district weekly + daily totals,
    per-camera-zone weekly totals), 2016-2026, current ones from the live site and older ones
    from the Wayback Machine.
  - Times Square Alliance: monthly "Pedestrian Counts Map" PDFs -> headline average daily
    pedestrians for the bowtie (2022-2026; live site + Wayback).
  - Grand Central Partnership: monthly "Ped Count Report" PDFs, 9 counter locations,
    Dec 2019 - Sep 2022 (Wayback only; the live site 403s). The "Last Year" column is kept for
    months not otherwise covered (pre-2020 baseline), with dates shifted -364 days.
Other BIDs checked publish nothing machine-readable (see project notes / report).
Output: data/raw/traffic/bid_ped_counts.parquet
"""
from __future__ import annotations

import io
import re
import shutil
import time
from datetime import date, datetime, timedelta

import pandas as pd
import pdfplumber

from traffic_common import TMP, get, save

CACHE = TMP / "bid"
WB = "https://web.archive.org"
NUM = r"\d{1,3}(?:,\d{3})+|\d+"
MON = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}

# Approximate intersection coordinates (lat, lon); coord_flag says how they were set.
GCP_LOC = {
    "5th Ave at 38th St": (40.7508, -73.9826), "5th Ave at 42nd St": (40.7532, -73.9808),
    "Lexington Ave at 42nd St": (40.7517, -73.9755), "3rd Ave at 42nd St": (40.7506, -73.9730),
    "Vanderbilt Ave at 42nd St": (40.7524, -73.9786), "5th Ave at 35th St": (40.7490, -73.9840),
    "5th Ave at 45th St": (40.7551, -73.9795), "Madison Ave at 45th St": (40.7549, -73.9784),
    "Lexington Ave at 51st St": (40.7570, -73.9715),
    "Grand Central Terminal": (40.7527, -73.9772), "Pershing Square Plaza West": (40.7518, -73.9780),
}
GDA_ZONES = [  # regex on location label -> intersection
    (r"^(?:W )?40 at 7|^7 at (?:W )?40", (40.7545, -73.9881)),
    (r"^7 at W ?37|^W ?37 at 7", (40.7525, -73.9895)),
    (r"^8 at W ?36|^W ?36 at 8", (40.7535, -73.9928)),
    (r"Broadway at 13[5-9]\d", (40.7516, -73.9878)),
    (r"Broadway at 14[1-4]\d", (40.7536, -73.9866)),
    (r"Broadway 1400", (40.7526, -73.9872)),
    (r"Broadway 1300", (40.7505, -73.9884)),
    (r"6th Av", (40.7528, -73.9851)),
]
GDA_CENTROID = (40.7535, -73.9890)
TSA_CENTROID = (40.7580, -73.9855)
MRI = "automated counters (MRI OnLocation, formerly Springboard)"


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _cdx(url: str, pattern: str) -> list[tuple[str, str]]:
    """Wayback captures (timestamp, original), 200 or revisit, whose URL matches pattern."""
    r = get(f"{WB}/cdx/search/cdx", timeout=300, params={
        "url": url, "matchType": "prefix", "fl": "timestamp,original", "collapse": "urlkey",
        "filter": ["!statuscode:[345].*", f"original:{pattern}"], "limit": 20000})
    return [tuple(l.split(" ", 1)) for l in r.text.splitlines() if " " in l]


def _live_links(page: str, pattern: str) -> list[str]:
    html = get(page, timeout=60).text
    return sorted({u.replace("&amp;", "&") for u in re.findall(r'href="([^"]+\.pdf)"', html)
                   if re.search(pattern, u)})


def _pdf_text(url: str, key: str) -> str | None:
    """Download (cached) and return page texts joined by form feed; None if not a usable PDF."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (re.sub(r"[^A-Za-z0-9._-]+", "_", key)[-150:])
    if not path.exists():
        try:
            path.write_bytes(get(url, timeout=120, tries=3).content)
        except RuntimeError as e:
            print(f"  download failed {url}: {e.__cause__ or e}", flush=True)
            return None
        time.sleep(1.0)  # be polite to the archive / BID sites
    try:
        with pdfplumber.open(path) as pdf:
            return "\f".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:  # pdfminer raises many types on bad files
        print(f"  unreadable PDF {url}: {type(e).__name__}: {e}", flush=True)
        return None


def _row(bid, loc, ll, flag, start, end, gran, count, metric, url):
    return dict(bid=bid, location_name=loc, lat=ll[0], lon=ll[1], coord_flag=flag,
                period_start=pd.Timestamp(start), period_end=pd.Timestamp(end),
                granularity=gran, count=float(count), metric=metric, source_url=url, method=MRI)


# ---------------- Garment District Alliance ----------------
def _gda_sources() -> dict[tuple[int, int], str]:
    src = {}
    for dom in ("garmentdistrict.nyc/", "garmentdistrictnyc.com/"):
        for ts, orig in _cdx(dom, ".*[Ff]ootfall.*\\.pdf"):
            m = re.search(r"wk(\d+)yr(\d{4})", orig, re.I)
            if m:
                src.setdefault((int(m[2]), int(m[1])), f"{WB}/web/{ts}id_/{orig}")
    for u in _live_links("https://garmentdistrict.nyc/market-research", r"(?i)footfall"):
        u = u if u.startswith("http") else "https://garmentdistrict.nyc" + u
        m = re.search(r"wk(\d+)yr(\d{4})", u, re.I)
        if m:
            src[(int(m[2]), int(m[1]))] = u
    return src


def _gda_parse(txt: str, url: str) -> list[dict]:
    """Handles the Springboard (2016-18) and MRI OnLocation (2019+) layouts."""
    m = re.search(r"(\d{2} \w{3} \d{4}) - (\d{2} \w{3} \d{4})", txt)
    if m:
        start, end = (datetime.strptime(x, "%d %b %Y").date() for x in m.groups())
    elif (m := re.search(r"(\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})", txt)):
        start, end = (datetime.strptime(x, "%m/%d/%Y").date() for x in m.groups())
    else:
        return []
    bid, out, seen = "Garment District Alliance", [], set()
    tot = re.search(rf"week commencing [^\n]*? was ({NUM})", txt)
    if tot:
        out.append(_row(bid, "District total", GDA_CENTROID, "bid_centroid", start, end,
                        "weekly", _num(tot[1]), "pedestrians", url))
    daily = re.search(rf"^((?:{NUM}) (?:(?:{NUM}) ){{6}}(?:{NUM}))$", txt, re.M)
    if daily:
        vals = [_num(v) for v in daily[1].split()]
        if tot and vals[7] == _num(tot[1]):  # sanity: this is the current-week row
            for i, v in enumerate(vals[:7]):
                d = start + timedelta(days=i)
                out.append(_row(bid, "District total", GDA_CENTROID, "bid_centroid", d, d,
                                "daily", v, "pedestrians", url))
    # Zone rows: "<name> <this week> ..." where the name ends in a corner, street no. or "Zone".
    for name, v in re.findall(rf"^(.+?(?: [NSEW]{{2}}| at \d{{4}}| Zone)) ({NUM}) .*%", txt, re.M):
        if name in seen:  # 2021+ reports repeat the table vs 2019 on later pages
            continue
        seen.add(name)
        ll = next((c for pat, c in GDA_ZONES if re.search(pat, name)), None)
        out.append(_row(bid, name, ll or GDA_CENTROID,
                        "intersection_approx" if ll else "bid_centroid",
                        start, end, "weekly", _num(v), "pedestrians", url))
    return out


# ---------------- Times Square Alliance ----------------
def _tsa_sources() -> list[str]:
    urls = [f"{WB}/web/{ts}id_/{o}" for ts, o in
            _cdx("timessquarenyc.org/sites/default/files/", ".*Pedestrian.*\\.pdf")]
    urls += _live_links("https://www.timessquarenyc.org/business-community/market-research-data",
                        r"Pedestrian%20Map|Pedestrian Map")
    return urls


def _tsa_parse(txt: str, url: str) -> list[dict]:
    m = re.search(r"TIMES SQUARE \| (\w+) (\d{4}) KEY INDICATORS", txt)
    v = re.search(r"Average Daily Visitors\s*\nPedestrian Counts Map\s*\n(" + NUM + ")", txt) \
        or re.search(r"Average Daily Visitors\s*\n(" + NUM + r")\s*\n", txt)
    if not (m and v and m[1].lower() in MON):
        return []
    y, mo = int(m[2]), MON[m[1].lower()]
    end = (pd.Timestamp(y, mo, 1) + pd.offsets.MonthEnd(0)).date()
    return [_row("Times Square Alliance", "Times Square bowtie (all counting zones)", TSA_CENTROID,
                 "bid_centroid", date(y, mo, 1), end, "monthly", _num(v[1]),
                 "avg_daily_pedestrians", url)]


# ---------------- Grand Central Partnership ----------------
def _gcp_sources() -> list[str]:
    return [f"{WB}/web/{ts}id_/{o}" for ts, o in
            _cdx("grandcentralpartnership.nyc/sites/default/files/uploads/reports/",
                 ".*Ped.*Count.*\\.pdf")]


def _gcp_parse(txt: str, url: str) -> list[dict]:
    txt = txt.replace("\f", "\n")
    m = re.search(r"(\d{2} \w{3} \d{4}) - (\d{2} \w{3} \d{4})", txt)
    tot = txt.split("Total Pedestrian Counts", 1)[-1].split("Average Pedestrian Counts by Weekday")
    if not m or len(tot) < 2:
        return []
    def row_re(lab):
        return re.search(rf"^({lab}) ((?:(?:{NUM}) ?)+)$", tot[0], re.M)
    cur = row_re("This Month|This Year|" + "|".join(k.title() for k in MON))
    prior = row_re("Last Year")
    # Location order of the totals rows = order of the weekday table that follows.
    names = []
    for nm in re.findall(rf"^([A-Z0-9][A-Za-z0-9 .'*]+?) (?:{NUM})(?: (?:{NUM})){{6}}$", tot[1], re.M):
        if re.search(r"Daily|Year|Change", nm):  # per-location detail pages start here
            break
        nm = nm.rstrip("*")
        if nm not in names:
            names.append(nm)
    start, end = (datetime.strptime(x, "%d %b %Y").date() for x in m.groups())
    out = []
    for r, shift, how in ((cur, 0, ""), (prior, 364, "; prior-year column, dates -364d")):
        vals = [_num(x) for x in r[2].split()] if r else []
        if not vals or len(vals) > len(names):
            continue
        for name, v in zip(names, vals):
            ll = GCP_LOC.get(name)
            row = _row("Grand Central Partnership", name, ll or (40.7527, -73.9772),
                       "intersection_approx" if ll else "bid_centroid",
                       start - timedelta(days=shift), end - timedelta(days=shift),
                       "monthly", v, "pedestrians", url)
            row["method"] += how
            out.append(row)
    return out


def _collect(name: str, urls, parser) -> list[dict]:
    rows, bad = [], []
    for i, u in enumerate(urls):
        txt = _pdf_text(u, f"{name}_{u.rsplit('/', 1)[-1]}_{i}")
        got = parser(txt, u) if txt else []
        (rows.extend(got) if got else bad.append(u))
    print(f"{name}: {len(urls)} PDFs, {len(urls) - len(bad)} parsed, {len(rows)} rows", flush=True)
    for u in bad:
        print(f"  no rows parsed from {u}", flush=True)
    return rows


def run() -> pd.DataFrame:
    gda = _gda_sources()
    rows = _collect("gda", [gda[k] for k in sorted(gda)], _gda_parse)
    rows += _collect("tsa", _tsa_sources(), _tsa_parse)
    rows += _collect("gcp", _gcp_sources(), _gcp_parse)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no BID pedestrian rows parsed")
    # Prior-year columns only fill the span before a location's first actual report.
    df["_prior"] = df["method"].str.contains("prior-year")
    first = df[~df._prior].groupby(["bid", "location_name"]).period_start.min()
    cut = df.set_index(["bid", "location_name"]).index.map(first)
    df = df[~df._prior | (df.period_start.values < cut.values)]
    df = (df.sort_values(["_prior"]).drop_duplicates(
        ["bid", "location_name", "period_start", "granularity", "metric"], keep="first")
        .drop(columns="_prior").sort_values(["bid", "granularity", "location_name", "period_start"])
        .reset_index(drop=True))
    save(df, "bid_ped_counts", source="Garment District Alliance, Times Square Alliance, Grand "
         "Central Partnership PDF reports (live sites + web.archive.org)",
         note="Text-layer PDF parse. coord_flag: intersection_approx or bid_centroid. GCP "
              "prior-year rows are approximate (-364d). TSA count = average daily pedestrians.")
    shutil.rmtree(CACHE, ignore_errors=True)
    return df


if __name__ == "__main__":
    run()
