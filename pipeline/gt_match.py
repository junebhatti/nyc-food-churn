"""Extract events and names from post metadata and match them to DOHMH businesses / SLA premises.

Name extraction is dictionary-based: every 1..6-word n-gram of the normalised title (or URL
slug) and every post label (EV Grieve / WordPress tags) is looked up in a dictionary of DOHMH
name variants. Generic variants (dictionary words, chains, place names that recur in titles)
are dropped. Candidates are then limited to the blog's ZIP area and to businesses that existed
around the post date. Ambiguous names (several businesses left) are resolved by a street address
in the title when one geocodes (PadGeocoder) to a candidate's BBL; otherwise left unmatched.

Output: events.parquet, one row per post with event, matched business, F/L/U, match details.
"""
from __future__ import annotations

import re
from collections import defaultdict

import numpy as np
import pandas as pd

from gt_common import OUT, RAW, classify, mnorm, norm, save
from gt_dohmh import SUFFIX as SUFFIX_WORDS, business_table, camis_table, variants

AREA_ZIPS = {
    "ev": {"10003", "10009", "10002", "10012"},
    "uws": {"10023", "10024", "10025", "10069", "10026"},
    "tribeca": {"10013", "10007", "10282", "10280", "10006", "10038", "10012", "10004"},
    "greenpoint": {"11222", "11211", "11249", "11206"},
}
AREA_BORO = {"ev": "MANHATTAN", "uws": "MANHATTAN", "tribeca": "MANHATTAN", "greenpoint": "BROOKLYN"}
CLOSE_LABEL = re.compile(r"closings|closures|now closed|store closing|continue to close|"
                         r"small business closure|possibly be closed", re.I)
OPEN_LABEL = re.compile(r"^new (restaurants|bars|cafes)|^openings$|restaurant opening|grand opening|"
                        r"\d{4} openings|greenpoint openings", re.I)
ROUNDUP = re.compile(r"\b(AND MORE|ALL SHUTTER|ROUNDUP|ROUND UP|SEEN AND HEARD|IN THE NEWS|GRIEVIEW|EATERWIRE|THE SHUTTER|SHUTTER TALLY|WEEK IN|REOPENINGS|THIS WEEK|WEEK IN|OPENINGS AND CLOSINGS|CLOSINGS AND OPENINGS|"
                     r"OPENINGS CLOSINGS|EVERY|ALL THE|BIGGEST|NOTABLE|\d+ (RESTAURANTS|PLACES|BARS))\b")
ADDR = re.compile(r"\b(\d{1,5}(?:-\d{1,3})?) ((?:EAST |WEST |E |W |NORTH |SOUTH )?(?:AVENUE [A-D]|AVE [A-D]|"
                  r"[A-Z0-9]+(?: [A-Z]+)?) (?:STREET|ST|AVENUE|AVE|PLACE|PL|BOULEVARD|BLVD|ROAD|RD|BROADWAY)?)\b")
FOOD = re.compile(r"\b(RESTAURANTS?|BARS?|CAFES?|COFFEE|PIZZ\w*|BAKERY|BAKESHOP|DELI|DINER|KITCHEN|SUSHI|"
                  r"BURGERS?|TACOS?|TAQUERIA|RAMEN|NOODLES?|WINE|BEER|PUB|TAVERN|GRILL|BISTRO|BAGELS?|BRUNCH|"
                  r"CHEF|EATERY|BBQ|BARBECUE|STEAK\w*|DUMPLINGS?|FALAFEL|THAI|CHINESE|ITALIAN|MEXICAN|INDIAN|"
                  r"JAPANESE|KOREAN|VEGAN|DONUTS?|DOUGHNUTS?|ICE CREAM|GELATO|TEA|JUICE|SPOT|SPEAKEASY|LOUNGE|"
                  r"COCKTAILS?|DIVE|SANDWICH\w*|SALAD|BUTCHER|FOOD|DINING|EATS|TRATTORIA|OSTERIA|CANTINA|"
                  r"BRASSERIE|LUNCHEONETTE|CREPE\w*|CHICKEN|SEAFOOD|OYSTER\w*)\b")
FOOD_LABEL = re.compile(r"restaurant|bars?\b|cafe|food|eat|drink|dining|coffee|pizza|bak", re.I)
MAX_BIZ_PER_NAME = 8      # name shared by more businesses citywide = chain / generic
MAX_TITLES_PER_NAME = 40  # name appearing in more posts = place name / generic word
WORDS = {w.strip().upper() for w in open("/usr/share/dict/words") if w.strip()}
STOPGRAM = {"EAST VILLAGE", "WEST VILLAGE", "LOWER EAST SIDE", "UPPER WEST SIDE", "GREENPOINT",
            "WILLIAMSBURG", "TRIBECA", "BROOKLYN", "MANHATTAN", "QUEENS", "NEW YORK", "SOHO", "NOHO",
            "AVENUE A", "AVENUE B", "AVENUE C", "AVENUE D", "ST MARKS", "ST MARKS PLACE", "BOWERY",
            "TOMPKINS SQUARE", "SECOND AVENUE", "FIRST AVENUE", "UNION SQUARE", "HARLEM", "BRONX",
            "CHELSEA", "MIDTOWN", "ASTORIA", "BUSHWICK", "FLATIRON", "NOLITA", "CHINATOWN",
            "LITTLE ITALY", "PARK SLOPE", "NOW OPEN", "COMING SOON", "SHUTTER ALERT", "FIRST LOOK",
            "EATER", "GRUB STREET", "AMSTERDAM", "COLUMBUS", "BROADWAY", "HUDSON", "NEW", "OPEN",
            "CLOSED", "CLOSING", "LAST DAY", "WEST SIDE", "UPPER EAST SIDE", "TIMES SQUARE"}


def load_posts() -> pd.DataFrame:
    parts = []
    for name in ("posts_blogs", "posts_wayback"):
        p = OUT / f"{name}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p))
        else:
            print(f"WARNING: {p.name} missing; run its fetch step first")
    df = pd.concat(parts, ignore_index=True)
    df["area"] = df["area"].fillna("nyc") if "area" in df else "nyc"
    df["labels"] = df["labels"].map(lambda x: list(x) if isinstance(x, (list, np.ndarray)) else [])
    return df


def post_event(title: str, labels: list[str]) -> str | None:
    ev = classify(title)
    if ev in ("notclose", "reopen", "relocate", "temp", "coming", "for_rent"):
        return ev
    lab_close = any(CLOSE_LABEL.search(l) for l in labels)
    lab_open = any(OPEN_LABEL.search(l) for l in labels)
    if ev is None:
        return "close" if lab_close and not lab_open else "open" if lab_open and not lab_close else None
    return ev


def name_dict(biz: pd.DataFrame) -> tuple[dict[str, set[int]], set[str]]:
    """variant -> businesses, plus the set of variants that are a full (unstripped) name."""
    d: dict[str, set[int]] = defaultdict(set)
    full: set[str] = set()
    for b, dba in zip(biz["biz"], biz["dba"]):
        n = mnorm(dba)
        full.update({n, n[4:] if n.startswith("THE ") else n})
        for v in variants(dba):
            d[v].add(b)
        toks = (n[4:] if n.startswith("THE ") else n).split()
        if len(toks) >= 3:  # "JOEY PEPPERONI PIZZA" is written "Joey Pepperoni"
            d[" ".join(toks[:2])].add(b)
    return d, full


STREET_RX = re.compile(r"\b(AVENUE [A-D]|AVE [A-D]|(?:\d+(?:ST|ND|RD|TH)?|FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|"
                       r"SEVENTH|EIGHTH|NINTH|TENTH|ELEVENTH|TWELFTH|[A-Z]{4,}) (?:STREET|ST|AVENUE|AVE|PLACE|PL|"
                       r"BOULEVARD|BLVD)|BOWERY|BROADWAY|HOUSTON|DELANCEY|BLEECKER|ST MARKS)\b")
NOT_STREET = {"GRUB", "SESAME", "MAIN", "THIS", "THAT", "SIDE", "WALL", "EVERY", "WHAT", "OPEN", "FROM", "INTO",
              "WITH", "OVER", "DOWN", "ALONG", "NEAR"}


def street_key(s: str) -> str:
    from gov_geocode import norm_street  # noqa: E402
    k = norm_street(s)
    k = re.sub(r"\b(EAST|WEST|NORTH|SOUTH)\b", " ", k)
    k = re.sub(r"\bST MARKS( PLACE)?\b", "SAINT MARKS PLACE", k)
    k = re.sub(r"\bSAINT MARKS( PLACE)?\b", "SAINT MARKS PLACE", k)
    k = re.sub(r"\b(HOUSTON|DELANCEY|BLEECKER)\b.*", r"\1 STREET", k)
    return re.sub(r"\s+", " ", k).strip()


def title_streets(t: str) -> set[str]:
    out = set()
    for m in STREET_RX.finditer(t):
        w = m.group(1)
        if w.split()[0] in NOT_STREET:
            continue
        out.add(street_key(w))
    return out


def usable(v: str, nbiz: int, is_full: bool = True) -> bool:
    if len(v.replace(" ", "")) < 4 or v in STOPGRAM or nbiz > MAX_BIZ_PER_NAME:
        return False
    toks = v.split()
    if not is_full and len(toks) == 1:  # "NINGBO" from "NINGBO CAFE"; not "BILLYS" (BILLY + S)
        t = toks[0]
        return len(t) >= 5 and t not in WORDS and not (t.endswith("S") and t[:-1] in WORDS)
    if not is_full and (len(toks) < 2 or all(t in WORDS or t.isdigit() for t in toks)
                        or toks[-1] in {"STREET", "AVENUE", "AVE", "ST", "PLACE", "BOULEVARD", "ROAD", "PARK", "SQUARE"}):
        return False  # stripped core made only of ordinary words ("GRAMERCY PARK" from "... BAR")
    if len(toks) == 1 and (toks[0] in WORDS or toks[0].isdigit()):
        return False
    if all(t in WORDS or t.isdigit() for t in toks) and len(toks) == 2 and nbiz > 3:
        return False
    return True


def ngrams(text: str) -> list[tuple[int, int, str]]:
    toks = mnorm(text).split()
    out = []
    for i in range(len(toks)):
        for n in range(min(6, len(toks) - i), 0, -1):
            out.append((i, n, " ".join(toks[i:i + n])))
    return out


def geocode_addresses(posts: pd.DataFrame) -> pd.Series:
    """BBL for a street address in the title (blogs with a known borough only)."""
    from gov_geocode import PadGeocoder  # noqa: E402 (heavy; only when needed)
    g = PadGeocoder()
    out = {}
    for i, t, a in zip(posts.index, posts["title"], posts["area"]):
        if a not in AREA_BORO:
            continue
        m = ADDR.search(norm(t))
        if m:
            r = g.one(m.group(1), m.group(2), None, AREA_BORO[a])
            if r.get("status") == "ok":
                out[i] = str(r["bbl"])
    print(f"title addresses geocoded: {len(out):,}", flush=True)
    return pd.Series(out, dtype=object)


def candidates_ok(b: pd.Series, ev: str, d: pd.Timestamp) -> bool:
    yr3 = pd.Timedelta(days=3 * 365)
    if pd.isna(b["F"]):
        return False
    if ev in ("open", "coming"):
        return b["last_snap"] >= d - pd.Timedelta(days=30) and d - yr3 <= b["F"] <= d + yr3
    return b["F"] <= d + pd.Timedelta(days=30) and b["L"] >= d - yr3


def match(posts: pd.DataFrame, biz: pd.DataFrame) -> pd.DataFrame:
    nd, full = name_dict(biz)
    # how many posts mention each variant (generic-name filter)
    hits = defaultdict(set)
    for pid, t in zip(posts.index, posts["title"]):
        for _, _, g in ngrams(t):
            if g in nd:
                hits[g].add(pid)
    ok_names = {v for v, bs in nd.items() if usable(v, min(len(bs), MAX_BIZ_PER_NAME), v in full)
                and len(hits.get(v, ())) <= MAX_TITLES_PER_NAME}
    chain = {v: len(nd[v]) > MAX_BIZ_PER_NAME for v in ok_names}
    B = biz.set_index("biz")
    bzip, bboro = B["zip"].to_dict(), B["boro"].to_dict()
    bstreet = {b: street_key(st) for b, st in B["street"].items() if isinstance(st, str)}
    bbl = B["bbl"].astype(str).str.replace(r"\.0$", "", regex=True).to_dict()
    addr_bbl = geocode_addresses(posts)
    rows = []
    for i, r in posts.iterrows():
        ev = r["event"]
        if r["pre_coverage"]:
            rows.append({"idx": i})
            continue
        found = []  # (rank, variant, [biz])
        for pos, n, g in ngrams(r["title"]):
            if g in ok_names:
                found.append(((0, pos, -n), g))
        ttoks = set(norm(r["title"]).split())
        for lab in r["labels"]:
            v = mnorm(lab)
            if not any(len(t) >= 4 and t not in SUFFIX_WORDS and t in ttoks for t in v.split()):
                continue
            v2 = v[4:] if v.startswith("THE ") else v
            for vv in {v, v2}:
                if vv in ok_names:
                    found.append(((1, 0, -len(vv.split())), vv))
        found.sort()
        zips = AREA_ZIPS.get(r["area"])
        best, n_names, amb, n_conflict = None, 0, 0, 0
        seen = set()
        tnorm = norm(r["title"])
        for rank, g in found:
            if g in seen:
                continue
            seen.add(g)
            cands = [b for b in nd[g] if (zips is None or bzip.get(b) in zips)
                     and candidates_ok(B.loc[b], ev, r["date"])]
            if not cands:
                continue
            streets = title_streets(re.sub(rf"\b{re.escape(g)}\b", " ", tnorm))
            conflict = False
            if streets:  # prefer candidates on a street named in the title
                c2 = [b for b in cands if bstreet.get(b) in streets]
                if c2:
                    cands = c2
                elif len(cands) == 1:
                    conflict = True  # kept, flagged: may be another location of the same name
                    n_conflict += 1
            if chain.get(g) and not (streets and not conflict and len(cands) == 1):
                continue  # chain name: only usable when a street pins down one location
            n_names += 1
            if len(cands) > 1 and i in addr_bbl.index:
                c2 = [b for b in cands if bbl.get(b) == addr_bbl[i]]
                cands = c2 or cands
            if len(cands) > 1:
                amb += 1
                continue
            if best is None:
                best = (g, cands[0], rank[0], conflict)
        row = {"idx": i, "n_names": n_names, "n_ambiguous": amb, "n_street_conflict": n_conflict,
               "addr_bbl": addr_bbl.get(i)}
        if best:
            row.update(matched_name=best[0], biz=best[1], via_label=best[2] == 1, street_conflict=best[3])
        rows.append(row)
    m = pd.DataFrame(rows).set_index("idx")
    out = posts.join(m)
    bcols = ["dba", "camis_list", "n_camis", "F", "first_seen", "L", "U", "last_snap", "zip", "boro", "bbl"]
    out = out.merge(biz[["biz"] + bcols], on="biz", how="left")
    return out


def sla_match(ev: pd.DataFrame) -> pd.Series:
    """For unmatched posts: does the name match an SLA on-premises licence in the area?"""
    s = pd.read_parquet(RAW / "gov" / "sla_licenses_nyc.parquet",
                        columns=["dba", "legal_name", "snap_premise_name", "zip", "on_premises",
                                 "start_date", "end_date"])
    s = s[s["on_premises"]]
    d = defaultdict(list)
    for col in ("dba", "snap_premise_name"):
        for nm, z, a, b in zip(s[col], s["zip"].astype(str).str[:5], s["start_date"], s["end_date"]):
            if isinstance(nm, str):
                n = norm(nm)
                n = n[4:] if n.startswith("THE ") else n
                if usable(n, 1) and not re.search(r"\b(STREET|AVENUE|AVE|PLACE|ROAD|WEST|EAST)$", n):
                    d[n].append(z)
    res = {}
    for i, r in ev[ev["biz"].isna()].iterrows():
        zips = AREA_ZIPS.get(r["area"])
        for _, _, g in ngrams(r["title"]):
            if g in d and g not in STOPGRAM and (zips is None or any(z in zips for z in d[g])):
                if zips is None and len(set(d[g])) > 1:
                    continue
                res[i] = g
                break
    return pd.Series(res, dtype=object)


def loose_match(ev: pd.DataFrame, biz: pd.DataFrame) -> pd.Series:
    """For unmatched posts: a DOHMH business in the area, alive around the post date, sharing any
    distinctive title word (>= 4 letters, not a dictionary word). None = the business is likely
    absent from DOHMH (or the post is not about a food business)."""
    tok: dict[str, list[int]] = defaultdict(list)
    for b, dba in zip(biz["biz"], biz["dba"]):
        for t in set(norm(dba).split()):
            if len(t) >= 4 and t not in WORDS:
                tok[t].append(b)
    B = biz.set_index("biz")
    res = {}
    for i, r in ev[ev["biz"].isna() & ~ev["pre_coverage"]].iterrows():
        zips = AREA_ZIPS.get(r["area"])
        for t in set(norm(r["title"]).split()):
            if len(t) < 4 or t in WORDS or t in STOPGRAM or t not in tok or len(tok[t]) > 300:
                continue
            for b in tok[t]:
                x = B.loc[b]
                if (zips is None or x["zip"] in zips) and candidates_ok(x, r["event"], r["date"]):
                    res[i] = x["dba"]
                    break
            if i in res:
                break
    return pd.Series(res, dtype=object)


def run() -> pd.DataFrame:
    posts = load_posts()
    posts["event"] = [post_event(t, l) for t, l in zip(posts["title"], posts["labels"])]
    posts["roundup"] = posts["title"].map(lambda t: bool(ROUNDUP.search(norm(t))) or len(re.findall(r"[,;]", t)) >= 3)
    # food-related by its words or labels (WordPress categories here are food / open-closed already;
    # Eater and Grub Street are food sites)
    posts["food_words"] = [bool(FOOD.search(norm(t))) or any(FOOD_LABEL.search(l) for l in ls)
                           for t, ls in zip(posts["title"], posts["labels"])]
    print(posts.groupby(["source", "event"], dropna=False).size().unstack(fill_value=0), flush=True)
    posts = posts[posts["event"].notna()].reset_index(drop=True)
    # DOHMH holds almost no business that closed before mid-2011: older posts are kept but not matched
    posts["pre_coverage"] = posts["date"] < pd.Timestamp("2011-07-01")
    c = camis_table()
    biz = business_table(c)
    print(f"CAMIS {len(c):,} -> businesses {len(biz):,}; latest full copy {c.attrs['latest_snapshot'].date()}",
          flush=True)
    ev = match(posts, biz)
    sla = sla_match(ev)
    ev["sla_name"] = sla.reindex(ev.index)
    ev["loose_dohmh_name"] = loose_match(ev, biz).reindex(ev.index)
    ev["food_post"] = (ev["food_words"] | ev["biz"].notna() | ev["sla_name"].notna()
                       | ev["source"].isin(["eater", "grubstreet", "tribecacitizen", "greenpointers"]))
    ev["labels"] = ev["labels"].map(lambda x: [l for l in x if l][:30])
    save(ev, "events")
    return ev


if __name__ == "__main__":
    run()
