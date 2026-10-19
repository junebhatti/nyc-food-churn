"""Manhattan Community Board 3 (East Village / LES / Chinatown) SLA & DCA Licensing Committee items,
parsed from the monthly full-board minutes PDFs on nyc.gov (2004-2026).

Each numbered committee item looks like
    5.      SakaMai (SakaMai LLC), 157 Ludlow St (op)
followed by a VOTE / withdrawn / approved line. Items cover new applications, renewals with complaint
history, transfers, alterations, corporate changes and sidewalk cafés: dated, addressed evidence that a
licensed bar/restaurant existed (or was proposed) at a premises in that month.

Needs `pdftotext` (poppler). Only nyc.gov is contacted (1 request/s).
"""
from __future__ import annotations

import json
import re
import subprocess
import time

import pandas as pd

from coverage_common import CACHE, SESSION, geocode, log, save

PAGE = "https://www.nyc.gov/site/manhattancb3/minutes/meeting-vote-records.page"
PDF_DIR = CACHE / "cb3_minutes"
TXT_DIR = CACHE / "cb3_txt"
LIC = {"op": "on_premises_liquor", "wb": "wine_beer", "b": "beer", "rw": "restaurant_wine",
       "w": "wine", "ow": "on_premises_wine", "tw": "tavern_wine", "hl": "hotel_liquor",
       "cl": "club_liquor", "cbw": "club_beer"}
SECTION_START = re.compile(r"^\s*SLA\s*(&|and)\s*(DCA|Economic)|^\s*SLA\b.{0,40}(Licensing|Committee)\s*$", re.I)
COMMITTEE = re.compile(r"^[A-Z][A-Za-z,&/ \-']{3,80}(Committee|Task Force|Subcommittee)\s*$")
ITEM = re.compile(r"^\s{0,6}(\d{1,3})\.\s+(\S.*)$")
SECTION_HDR = re.compile(r"^[A-Z][A-Za-z'’ /&\-–]{3,70}$")


def download():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    html = SESSION.get(PAGE, timeout=60).text
    paths = sorted(set(re.findall(r'href="(/assets/manhattancb3/downloads/minutes/[^"]+\.pdf)"', html)))
    if not paths:
        raise RuntimeError("no minutes PDFs found on CB3 page (layout changed?)")
    for p in paths:
        f = PDF_DIR / p.rsplit("/", 1)[1]
        if f.exists() and f.stat().st_size:
            continue
        r = SESSION.get("https://www.nyc.gov" + p, timeout=120)
        r.raise_for_status()
        f.write_bytes(r.content)
        time.sleep(1)
    log(f"cb3: {len(paths)} minutes PDFs")


def to_text():
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(PDF_DIR.glob("*.pdf")):
        t = TXT_DIR / (f.stem + ".txt")
        if not t.exists():
            subprocess.run(["pdftotext", "-layout", str(f), str(t)], check=True)


def split_item(body: str):
    """'Quality Eats (Downwind LLC), 177 Ludlow St btwn X & Y (op/alt...)' -> parts."""
    lic = None
    m = re.search(r"\(([^()]*)\)\s*$", body)
    if m and re.match(r"\s*(op|wb|b|rw|w|ow|tw|hl|cl|cbw|n/a|upgrade|alt|trans|corp|removal)\b", m.group(1), re.I):
        lic, body = m.group(1).strip(), body[:m.start()].strip()
    m = re.match(r"^(?P<name>.+?),\s+(?P<addr>\d[\w\-]*(?:\s*1/2)?\s+.+)$", body)
    if not m:
        return None
    name, addr = m.group("name").strip(), m.group("addr").strip()
    addr = re.split(r"\s*@|\s+(?:btwn|btw|bwtn|betw|between|b/t|bet\.?|aka|a/k/a|corner|at|near|on)\b|"
                    r"\s+(?:\d+(?:st|nd|rd|th)\s+(?:Ave|St)|Ave\s+[A-D]|Bowery|Allen|Essex)\s*&|\s*\(|;|\.\s",
                    addr, 1, flags=re.I)[0]
    addr = re.split(r",", addr, 1)[0].strip()
    legal = None
    m2 = re.match(r"^(?P<dba>.*?)\s*\((?P<legal>[^()]+)\)\s*$", name)
    if m2:
        name, legal = m2.group("dba").strip(), m2.group("legal").strip()
    if re.match(r"(?i)^(to be determined|tbd|n/?a|none)$", name):
        name = None
    hm = re.match(r"^(\d[\w\-]*(?:\s*1/2)?)\s+(.+)$", addr)
    if not hm:
        return None
    return {"name": name, "legal_name": legal, "address": addr, "house": hm.group(1), "street": hm.group(2),
            "lic_raw": lic}


def outcome(lines):
    t = " ".join(x.strip() for x in lines[:6]).lower()
    for k, pat in [("withdrawn", r"\bwithdr[ae]wn|\bwithdraw"), ("laid_over", r"laid over|lay over|layover"),
                   ("deny_unless_stips", r"deny.{0,120}unless"), ("approved", r"approv|no objection|support"),
                   ("denied", r"\bden(y|ied)|oppos"), ("no_vote", r"no vote|no action")]:
        if re.search(pat, t):
            return k
    return None


def parse_file(path):
    m = re.search(r"(\d{4})-(\d{2})", path.stem)
    month = f"{m.group(1)}-{m.group(2)}"
    lines = path.read_text(errors="replace").splitlines()
    out, in_sla, section, i = [], False, None, 0
    while i < len(lines):
        ln = lines[i]
        if SECTION_START.search(ln):
            in_sla, section = True, None
            i += 1
            continue
        if in_sla and COMMITTEE.match(ln.strip()) and not SECTION_START.search(ln) and not ln.startswith(" "):
            in_sla = False
        if not in_sla:
            i += 1
            continue
        s = ln.strip()
        if SECTION_HDR.match(s) and not ln.startswith("   ") and not s.lower().startswith(("vote", "withdrawn")):
            section = s
        im = ITEM.match(ln)
        if im:
            body = im.group(2).strip()
            j = i + 1
            # wrapped item header: keep appending until the licence-code parenthesis closes
            while j < len(lines) and body.count("(") > body.count(")") and j - i < 4:
                body += " " + lines[j].strip()
                j += 1
            k = j
            while k < len(lines) and not ITEM.match(lines[k]) and k - j < 8:
                k += 1
            p = split_item(re.sub(r"\s+", " ", body))
            if p:
                p.update(month=month, item=int(im.group(1)), section=section, outcome=outcome(lines[j:k]),
                         file=path.name, raw=body[:300])
                out.append(p)
            i = j
            continue
        i += 1
    return out


def lic_class(raw):
    if not raw:
        return None
    code = re.split(r"[/ ,]", raw.strip().lower(), 1)[0]
    return LIC.get(code, code)


def run():
    download()
    to_text()
    rows = []
    for t in sorted(TXT_DIR.glob("*.txt")):
        rows += parse_file(t)
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("cb3 parser found no items")
    df["license_class"] = df["lic_raw"].map(lic_class)
    sec = df["section"].fillna("").str.lower()
    df["item_kind"] = "other"
    for k, pat in [("new_application", r"new|within .*area|saturat|resolution area|500.?foot|500 ft|"
                                        r"upgrade|method of operation"),
                   ("renewal", r"renewal"), ("transfer", r"transfer|corporate|change"), ("alteration", r"alteration"),
                   ("sidewalk_cafe", r"sidewalk|caf[eé]"), ("dca", r"dca|cabaret|amusement")]:
        df.loc[sec.str.contains(pat) & df["item_kind"].eq("other"), "item_kind"] = k
    df["source"] = "cb3_minutes"
    df["source_id"] = df["month"] + "#" + df["item"].astype(str) + "#" + df["file"]
    df["boro"] = 1
    df["zip"] = None
    df["start_date"] = pd.to_datetime(df["month"] + "-01")
    df["first_seen"] = df["start_date"]
    df["last_seen"] = df["start_date"]
    df["category"] = "bar_or_restaurant_licensed"
    df.loc[df["item_kind"].eq("sidewalk_cafe") & df["license_class"].isna(), "category"] = "restaurant_cafe"
    df["category_raw"] = df["section"]
    df["extra"] = [json.dumps({"outcome": o, "lic": l}) for o, l in zip(df["outcome"], df["lic_raw"])]
    df = geocode(df)
    log(f"cb3 items {len(df):,}; months {df['month'].nunique()}; geocoded {df['bbl'].notna().mean():.1%}")
    return save(df, "cb3_sla_items", source="Manhattan CB3 full-board minutes (nyc.gov)", url=PAGE,
                note="One row per SLA/DCA committee agenda item in the monthly minutes, 2004-2026. "
                     "start_date = minutes month (committee met that month). Covers contested/new/renewal items, "
                     "not every licence in the district. outcome parsed from the vote text.")
