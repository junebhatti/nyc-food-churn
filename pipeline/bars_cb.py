"""Community-board liquor-licence items (2009-2016) from Wayback copies of CB PDFs on nyc.gov.

Boards: Manhattan CB1 (resolutions, full-board minutes), CB2 (full-board minutes, monthly SLA
resolutions), CB4/5/7 (if archived), CB10 (economic-development committee + general-board minutes),
CB12 (licensing committee / board minutes), Brooklyn CBs where archived. CB3 is in
data/raw/coverage/cb3_sla_items.parquet (coverage agent) and is not repeated here.

PDF layouts differ across boards and years, so the parser is generic: it finds street addresses that
sit within a short window of liquor-licence words (liquor, wine, beer, SLA, on-premises, tavern...),
takes the text before the address on that line as the applicant name, and dates the item by the
meeting date (file name, else the first date in the document). One row per (file, address).

Steps: enumerate (CDX, cached) -> download (archive.org, one client, >=3 s) -> pdftotext -> parse ->
geocode (PadGeocoder via coverage_common.geocode) -> data/raw/bars/cb_sla_items.parquet
(same columns as cb3_sla_items).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from urllib.parse import unquote

import pandas as pd

from bars_common import OUT, cdx, ia_get

CACHE = OUT / "_cache"
PDF_DIR = CACHE / "cb_pdf"
TXT_DIR = CACHE / "cb_txt"
CDX_FILE = CACHE / "cb_cdx.json"

# (board id, CDX prefix, borough code, regex the path must match to be an SLA-bearing document)
BOARDS = [
    ("mn01", "www.nyc.gov/html/mancb1/downloads/pdf/", 1, r"/(resolutions|fbm_minutes)/"),
    ("mn02", "www.nyc.gov/html/mancb2/downloads/pdf/", 1, r"fullboard|full%20board|monthly_cb2_resolutions/.*sla"),
    ("mn04", "www.nyc.gov/html/mancb4/downloads/pdf/", 1, r"[^/]*(minute|\bsla\b|liquor|blpn?\b)[^/]*$"),
    ("mn05", "www.nyc.gov/html/mancb5/downloads/pdf/", 1, r"minute|sla|liquor|resolution"),
    ("mn07", "www.nyc.gov/html/mancb7/downloads/pdf/", 1, r"minute|sla|liquor|resolution|business"),
    ("mn10", "www.nyc.gov/html/mancb10/downloads/pdf/", 1, r"/economic/.*minute|/gbm/.*min|/economic/.*agenda|sla"),
    ("mn12", "www.nyc.gov/html/mancb12/downloads/pdf/", 1, r"licens|minute|resolution|agenda_20|sla|newapp"),
    ("bk01", "www.nyc.gov/html/bkncb1/downloads/pdf/", 3, r"minute|sla|liquor|resolution|agenda"),
    ("bk02", "www.nyc.gov/html/bkncb2/downloads/pdf/", 3, r"minute|sla|liquor|resolution|agenda"),
    ("bk03", "www.nyc.gov/html/bkncb3/downloads/pdf/", 3, r"minute|sla|liquor|resolution|agenda"),
    ("bk06", "www.nyc.gov/html/bkncb6/downloads/pdf/", 3, r"minute|sla|liquor|resolution|agenda"),
    ("bk08", "www.nyc.gov/html/bkncb8/downloads/pdf/", 3, r"minute|sla|liquor|resolution|agenda"),
]
YEAR_MIN, YEAR_MAX = 2009, 2014
MAX_BYTES = 6_000_000   # bigger files are scanned packets with no text layer
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
                                          "oct", "nov", "dec"])}


# ---------------------------------------------------------------- enumerate / download
def enumerate_pdfs() -> dict:
    cache = json.loads(CDX_FILE.read_text()) if CDX_FILE.exists() else {}
    for board, prefix, _, _ in BOARDS:
        if board in cache:
            continue
        rows = cdx(prefix, matchType="prefix", to="2017", filter=["mimetype:application/pdf", "statuscode:200"],
                   fl="original,timestamp,length", limit=20000)
        cache[board] = rows
        CDX_FILE.write_text(json.dumps(cache))
        print(f"  cdx {board}: {len(rows)} captures", flush=True)
    return cache


def file_date(url: str, text: str | None = None):
    """Meeting date from the file name (many conventions), else None."""
    name = unquote(url.rsplit("/", 1)[-1]).lower()
    path = unquote(url).lower()
    m = re.search(r"(?<!\d)(\d{1,2})[-.](\d{1,2})[-.](\d{2})(?!\d)", name)  # yy-mm-dd (CB1) or mm-dd-yy
    if m:
        a, b, c = (int(x) for x in m.groups())
        if a >= 80 and 1 <= b <= 12:       # CB1 1980s-90s resolutions: 89-12-12
            return pd.Timestamp(1900 + a, b, 1)
        if 1 <= b <= 12 and a <= 16 and c <= 31 and not (a <= 12 and b > 12):
            return pd.Timestamp(2000 + a, b, 1)
        if 1 <= a <= 12 and b <= 31 and c <= 16:
            return pd.Timestamp(2000 + c, a, 1)
    m = re.search(r"(?<!\d)(0[89]|1[0-6])(\d{2})(\d{2})(?!\d)", name)     # 090922
    if m and 1 <= int(m.group(2)) <= 12:
        return pd.Timestamp(2000 + int(m.group(1)), int(m.group(2)), 1)
    m = re.search(r"(20[01]\d)[_\-]?(\d{2})(?!\d)", name)                 # agenda_201006 / 2010_02
    if m and 1 <= int(m.group(2)) <= 12:
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), 1)
    mon = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[^a-z0-9]{0,3}(\d{1,2}[^0-9]{1,3})?"
                    r"(20[01]\d|(?<!\d)1\d(?!\d))", name)
    if mon:
        y = int(mon.group(3))
        return pd.Timestamp(y if y >= 2000 else 2000 + y, MONTHS[mon.group(1)], 1)
    m = re.search(r"(?<![a-z0-9])(\d{1,2})[_\-.](\d{2})(?:_for_merge)?(?:\.pdf)", name)        # GBM-min-6-14.pdf, Eco_Dev_Min_10_14
    if m and 1 <= int(m.group(1)) <= 12 and 9 <= int(m.group(2)) <= 16:
        return pd.Timestamp(2000 + int(m.group(2)), int(m.group(1)), 1)
    mon = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", name)
    yr = re.search(r"(20[01]\d)", path)
    fm = re.search(r"/(20[01]\d)_(\d{2})/", path)   # CB4 agendas/2009_07/
    if fm and 1 <= int(fm.group(2)) <= 12:
        return pd.Timestamp(int(fm.group(1)), int(fm.group(2)), 1)
    if not mon:   # CB4 style folder: /downloads/pdf/November 2014/...
        fm = re.search(r"/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(20[01]\d)/", path)
        if fm:
            return pd.Timestamp(int(fm.group(2)), MONTHS[fm.group(1)], 1)
    if mon and yr:
        return pd.Timestamp(int(yr.group(1)), MONTHS[mon.group(1)], 1)
    if text:
        m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                      r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(20[01]\d)", text[:3000])
        if m:
            return pd.Timestamp(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1)
    return None


def text_date(text: str):
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                  r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+(20[01]\d)", text[:1500])
    return pd.Timestamp(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1) if m else None


def select(cache: dict) -> pd.DataFrame:
    rows = []
    for board, prefix, boro, pat in BOARDS:
        for r in cache.get(board, []):
            u = r["original"].replace(":80/", "/")
            if f"/{prefix.split('/')[2]}/" not in u.lower() + "/":   # mancb1 prefix also matches mancb10/12
                continue
            if not re.search(pat, unquote(u).lower()):
                continue
            rows.append({"board": board, "boro": boro, "url": u, "ts": r["timestamp"], "length": int(r["length"] or 0)})
    d = pd.DataFrame(rows)
    d["key"] = d["url"].str.lower().map(unquote)
    d = d.sort_values("ts").drop_duplicates("key", keep="last")
    d["date"] = d["url"].map(file_date)
    yr = d["date"].dt.year
    keep = (yr.between(YEAR_MIN, YEAR_MAX) | d["date"].isna()) & d["length"].le(MAX_BYTES)
    path = d["url"].map(unquote)
    keep &= ~path.str.contains(r"201[5-9]", regex=True)   # path says 2015+
    old = path.str.contains(r"(?:19[89]\d|200[0-8])", regex=True) & ~path.str.contains(r"(?:2009|201[0-4])", regex=True)
    keep &= ~(old & d["date"].isna())                      # path says pre-2009
    return d[keep].reset_index(drop=True)


def fname(row) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", unquote(row["url"].split("/downloads/pdf/", 1)[-1]))
    return f"{row['board']}__{base}"[:180]


def download(sel: pd.DataFrame) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    order = {"mn01": 0, "mn02": 1, "mn10": 2, "mn12": 3}
    sel = sel.assign(o=sel["board"].map(order).fillna(9)).sort_values(["o", "length"])
    done = {p.name for p in TXT_DIR.glob("*.txt")} | {p.name for p in (CACHE / "cb_bad").glob("*")}
    todo = [r for _, r in sel.iterrows() if fname(r) + ".txt" not in done]
    print(f"  download: {len(todo)} of {len(sel)} PDFs to fetch", flush=True)
    for i, r in enumerate(todo):
        try:
            resp = ia_get(f"http://web.archive.org/web/{r['ts']}id_/{r['url']}", timeout=180)
        except RuntimeError as e:
            print(f"  FAIL {r['url']}: {e}", flush=True)
            continue
        if resp.status_code != 200 or not resp.content.lstrip()[:5].startswith(b"%PDF"):
            print(f"  skip {resp.status_code} {r['url'][:120]}", flush=True)
            (CACHE / "cb_bad").mkdir(exist_ok=True)
            (CACHE / "cb_bad" / (fname(r) + ".txt")).write_text(f"HTTP {resp.status_code}")
            continue
        # keep only the text layer (PDFs total >1 GB); a PDF with no text leaves an empty .txt
        pdf = PDF_DIR / fname(r)
        pdf.write_bytes(resp.content)
        p = subprocess.run(["pdftotext", "-layout", str(pdf), str(TXT_DIR / (pdf.name + ".txt"))],
                           capture_output=True)
        if p.returncode != 0:
            print(f"  pdftotext failed {pdf.name}: {p.stderr[:200]!r}", flush=True)
            (CACHE / "cb_bad").mkdir(exist_ok=True)
            (CACHE / "cb_bad" / (pdf.name + ".txt")).write_text(p.stderr.decode(errors="replace")[:500])
        pdf.unlink()
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}", flush=True)


def to_text() -> None:
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(PDF_DIR.glob("*")):
        t = TXT_DIR / (f.name + ".txt")
        if t.exists():
            continue
        p = subprocess.run(["pdftotext", "-layout", str(f), str(t)], capture_output=True)
        if p.returncode != 0:
            print(f"  pdftotext failed {f.name}: {p.stderr[:200]!r}", flush=True)


# ---------------------------------------------------------------- parse
SUFFIX = (r"(?:Street|St\b\.?|Avenue|Ave\b\.?|Av\b\.?|Place|Pl\b\.?|Boulevard|Blvd\b\.?|Road|Rd\b\.?|Lane|Ln\b\.?|"
          r"Slip|Square|Sq\b\.?|Plaza|Terrace|Way|Drive|Dr\b\.?|Alley|Row|Parkway|Pkwy\b\.?|Court|Ct\b\.?)")
ORD = r"\d{1,3}(?:st|nd|rd|th)?"
NAMED_AVE = (r"(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|Eleventh|Twelfth|Lexington|Madison|"
             r"Park|Amsterdam|Columbus|West End|York|Lenox|Malcolm X|Adam Clayton Powell(?: Jr\.?)?|Frederick Douglass|"
             r"St\.? Nicholas|Convent|Edgecombe|Fort Washington|Wadsworth|Audubon|Flatbush|Atlantic|Myrtle|Bedford|"
             r"Nostrand|Franklin|Vanderbilt|DeKalb|Fulton|Court|Smith|Union|Graham|Manhattan|Nassau|Driggs|Wythe|Kent|"
             r"Berry|Metropolitan|Grand|Havemeyer|Knickerbocker|Wilson|Irving|Bushwick|Flushing|Washington|Classon|"
             r"Lafayette|Greene|Gates|Putnam|Willoughby|Ralph|Utica|Rogers|Coney Island|Ocean|Church|Cortelyou|"
             r"Avenue [A-D]|Seventh|Fifth|Fourth|Third)")
STREET = (rf"(?:(?:East|West|North|South|E\.?|W\.?|N\.?|S\.?)\s+)?"
          rf"(?:{ORD}\s+{SUFFIX}|{NAMED_AVE}\s+{SUFFIX}|Avenue\s+(?:of\s+the\s+Americas|[A-D]\b)|Broadway|Bowery|"
          rf"(?:[A-Z][a-zA-Z'\.]+\s+){{1,3}}{SUFFIX}|[A-Z][a-zA-Z'\.]+\s+{SUFFIX})")
ADDR = re.compile(rf"(?<![\d/$#\-])(\d{{1,5}}(?:-\d{{1,4}})?[A-Z]?(?:\s?1/2)?)\s+({STREET})")
LIQ = re.compile(r"liquor|\bwine\b|\bbeer\b|\bSLA\b|on[- ]premise|\btavern|\bbar\b|alcohol|\bOP\b|\bcabaret\b|"
                 r"method of operation|500[- ]f(oo|ee)t", re.I)
NOT_STREET = re.compile(r"^(?:\d+\s+)?(?:Room|Floor|Suite|Seats?|Tables?|Chairs?|Hours?|Patrons?|Persons?|Feet|"
                        r"Units?|Members?|Votes?|Days?|Am|Pm)\b", re.I)


ABBR = [(r"\bSTREET\b", "ST"), (r"\bAVENUE\b|\bAV\b", "AVE"), (r"\bPLACE\b", "PL"), (r"\bWEST\b", "W"),
        (r"\bEAST\b", "E"), (r"\bBOULEVARD\b", "BLVD"), (r"\bSQUARE\b", "SQ")]


def street_key(street: str) -> str:
    s = re.sub(r"[.,]", "", street.upper())
    for a, b in ABBR:
        s = re.sub(a, b, s)
    s = re.sub(r"(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    return re.sub(r"[^A-Z0-9]", "", s)


def parse_text(text: str):
    lines = text.splitlines()
    flat = [re.sub(r"\s+", " ", ln).strip() for ln in lines]
    out, seen = [], set()
    for i, ln in enumerate(flat):
        for m in ADDR.finditer(ln):
            street = re.sub(r"\s+", " ", m.group(2)).strip()
            if NOT_STREET.match(street) or len(street) < 4:
                continue
            ctx = " ".join(flat[max(0, i - 3): i + 4])
            if not LIQ.search(ctx):
                continue
            house = m.group(1).replace(" ", "")
            key = (house.upper(), street_key(street))
            if key in seen:
                continue
            seen.add(key)
            pre = ln[: m.start()].strip(" ,;:-–(")
            pre = re.sub(r"^(?:\d{1,3}[.)]\s*|[a-z][.)]\s+|Re:?\s*|Resolution\s+(?:re|regarding)?:?\s*)", "", pre, flags=re.I)
            name = pre[-120:].strip(" ,;:-–") or None
            legal = None
            mm = re.search(r"(.*?)\s*\(([^()]{3,80})\)\s*$", name or "")
            if mm:
                name, legal = mm.group(1).strip() or None, mm.group(2).strip()
            if not name or re.match(r"^\d", name or ""):
                after = (ln[m.end():] + " " + (flat[i + 1] if i + 1 < len(flat) else ""))
                fm = re.search(r"licen[sc]es?\s+(?:application\s+)?for\s+(.{3,120}?)(?:[.;]\s|$)", after, re.I)
                name = fm.group(1).strip(" ,") if fm else None
            dba = re.search(r"(?:d/b/a|dba)\s+(.+)$", name or "", re.I)
            if dba:
                legal, name = name[: dba.start()].strip(" ,") or legal, dba.group(1).strip()
            lic = re.search(r"\b(OP|WB|RW|TW|HL|BW|Beer|Wine|Liquor|On[- ]Premises?)\b", ctx)
            if name:
                name = re.sub(r"\s*[–\-]+\s*Resolution\s*$", "", name).strip(" ,;:-–") or None
            zm = re.match(r"\s*,?\s*(?:New York,?\s*(?:NY)?\s*)?(1[01]\d{3})\b", ln[m.end():])
            out.append({"zip": zm.group(1) if zm else None, "name": name, "legal_name": legal, "address": f"{house} {street}", "house": house,
                        "street": street, "lic_raw": lic.group(1) if lic else None, "raw": ctx[:300], "line": i})
    return out


def lic_class(raw):
    if not raw:
        return None
    r = raw.lower().replace("-", " ")
    return {"op": "on_premises_liquor", "liquor": "on_premises_liquor", "on premises": "on_premises_liquor",
            "on premise": "on_premises_liquor", "wb": "wine_beer", "bw": "wine_beer", "rw": "restaurant_wine",
            "tw": "tavern_wine", "hl": "hotel_liquor", "beer": "beer", "wine": "wine"}.get(r, r)


def item_kind(ctx: str) -> str:
    c = ctx.lower()
    for k, pat in [("transfer", r"transfer|corporate change|change of (?:ownership|corp)"),
                   ("alteration", r"alteration"), ("renewal", r"renewal"),
                   ("new_application", r"new application|new license|application for|applicant|upgrade|"
                                       r"method of operation|500.?f(oo|ee)t"),
                   ("sidewalk_cafe", r"sidewalk caf"), ("dca", r"cabaret|dca")]:
        if re.search(pat, c):
            return k
    return "other"


def outcome(ctx: str):
    t = ctx.lower()
    for k, pat in [("withdrawn", r"withdr[ae]w"), ("laid_over", r"laid over|lay over|layover"),
                   ("deny_unless_stips", r"deny.{0,120}unless"), ("denied", r"\bden(y|ied)\b|oppos"),
                   ("approved", r"approv|no objection|support|recommends? (?:approval|that)")]:
        if re.search(pat, t):
            return k
    return None


def parse_all(sel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in sel.iterrows():
        t = TXT_DIR / (fname(r) + ".txt")
        if not t.exists():
            continue
        text = t.read_text(errors="replace")
        # header date (meeting date) wins; file-name conventions are ambiguous (yy-mm-dd vs mm-dd-yy)
        date = text_date(text) or (r["date"] if pd.notna(r["date"]) else None)
        if date is None or not (YEAR_MIN <= date.year <= YEAR_MAX):
            continue
        for it in parse_text(text):
            it.update(board=r["board"], boro=r["boro"], month=date.strftime("%Y-%m"), file=t.name, url=r["url"],
                      wayback_ts=r["ts"])
            rows.append(it)
    return pd.DataFrame(rows)


def run(steps=("enumerate", "download", "text", "parse")) -> pd.DataFrame | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = enumerate_pdfs()
    sel = select(cache)
    sel.to_csv(CACHE / "cb_selected.csv", index=False)
    print(f"cb: {len(sel)} PDFs selected:", sel["board"].value_counts().to_dict(), flush=True)
    if "download" in steps:
        download(sel)
    to_text()
    if "parse" not in steps:
        return None
    sys.path.insert(0, str(OUT.parents[2] / "pipeline"))
    from coverage_common import geocode   # reuse coverage agent's PadGeocoder wrapper (read-only)
    df = parse_all(sel)
    if df.empty:
        raise RuntimeError("cb parser found no items")
    df["item"] = df.groupby("file").cumcount() + 1
    df["section"] = None
    df["outcome"] = df["raw"].map(outcome)
    df["license_class"] = df["lic_raw"].map(lic_class)
    df["item_kind"] = df["raw"].map(item_kind)
    df["source"] = "cb_" + df["board"]
    df["source_id"] = df["month"] + "#" + df["item"].astype(str) + "#" + df["file"]
    df["start_date"] = pd.to_datetime(df["month"] + "-01")
    df["end_date"] = pd.NaT
    df["first_seen"] = df["start_date"]
    df["last_seen"] = df["start_date"]
    df["category"] = "bar_or_restaurant_licensed"
    df.loc[df["item_kind"].eq("sidewalk_cafe") & df["license_class"].isna(), "category"] = "restaurant_cafe"
    df["category_raw"] = None
    df["extra"] = [json.dumps({"outcome": o, "lic": l, "board": b, "url": u})
                   for o, l, b, u in zip(df["outcome"], df["lic_raw"], df["board"], df["url"])]
    df["lat"] = float("nan")
    df["lon"] = float("nan")
    df = geocode(df)
    cols = list(pd.read_parquet(OUT.parent / "coverage" / "cb3_sla_items.parquet").columns)
    for c in cols:
        if c not in df:
            df[c] = None
    df = df[cols + ["board", "url", "wayback_ts"]]
    for c in ("start_date", "first_seen", "last_seen"):
        df[c] = pd.to_datetime(df[c]).dt.date
    df.to_parquet(OUT / "cb_sla_items.parquet", index=False)
    print(f"cb items {len(df):,}; files {df['file'].nunique()}; geocoded {df['bbl'].notna().mean():.1%}; "
          f"by board {df['board'].value_counts().to_dict()}", flush=True)
    return df


if __name__ == "__main__":
    run(tuple(sys.argv[1:]) or ("enumerate", "download", "text", "parse"))
