"""Geocoding: a local PAD/SND address matcher (no network, ~1M addresses/min) plus an evaluation
against NYC GeoSearch on a stratified sample of 200 tricky addresses with known BBLs.

    python gov_geocode.py build   # PAD/SND -> data/raw/gov/pad_addr.parquet, snd_streets.parquet
    python gov_geocode.py eval    # sample + GeoSearch + local matcher -> geocode_eval.parquet

Library use (other pipeline steps):
    from gov_geocode import PadGeocoder
    g = PadGeocoder(); g.geocode_df(df, house="building", street="street", zip="zip", boro="boro")
"""
from __future__ import annotations

import io
import math
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from gov_common import OUT, SESSION, get, save

PAD_URL = "https://data.cityofnewyork.us/download/bc8t-ecyu/application%2Fzip"
PAD_ZIP = OUT / "pad_dl" / "pad.zip"

ABBR = {
    "ST": "STREET", "STR": "STREET", "AVE": "AVENUE", "AV": "AVENUE", "AVN": "AVENUE",
    "PL": "PLACE", "BLVD": "BOULEVARD", "BL": "BOULEVARD", "RD": "ROAD", "DR": "DRIVE",
    "PKWY": "PARKWAY", "PKY": "PARKWAY", "TPKE": "TURNPIKE", "TPK": "TURNPIKE", "HGWY": "HIGHWAY", "BLV": "BOULEVARD", "HWY": "HIGHWAY", "SQ": "SQUARE",
    "LN": "LANE", "CT": "COURT", "TER": "TERRACE", "TERR": "TERRACE", "EXPY": "EXPRESSWAY",
    "PLZ": "PLAZA", "CIR": "CIRCLE", "HTS": "HEIGHTS", "BWAY": "BROADWAY", "BDWY": "BROADWAY",
    "W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH", "FT": "FORT", "MT": "MOUNT",
    "CTR": "CENTER", "BCH": "BEACH", "ESPL": "ESPLANADE", "SLP": "SLIP", "WAY": "WAY",
}
WORD_ORD = {"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5", "SIXTH": "6",
            "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9", "TENTH": "10", "ELEVENTH": "11",
            "TWELFTH": "12"}
BORO = {"MANHATTAN": 1, "NEW YORK": 1, "NY": 1, "MN": 1, "1": 1, "BRONX": 2, "THE BRONX": 2,
        "BX": 2, "2": 2, "BROOKLYN": 3, "BK": 3, "KINGS": 3, "3": 3, "QUEENS": 4, "QN": 4,
        "4": 4, "STATEN ISLAND": 5, "SI": 5, "RICHMOND": 5, "5": 5}


def norm_street(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"[.,#'`]", " ", s.upper())
    s = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", s)  # 4TH -> 4
    s = re.sub(r"\b(\d+)([A-Z]{2,})\b", r"\1 \2", s)  # 37AVE -> 37 AVE
    toks = s.split()
    out = []
    for i, t in enumerate(toks):
        if t == "ST" and i == 0 and len(toks) > 1 and not toks[1].isdigit():
            t = "SAINT"
        else:
            t = ABBR.get(t, t)
        t = WORD_ORD.get(t, t) if i + 1 < len(toks) and toks[i + 1] in (
            "AVENUE", "AVE", "AV", "STREET", "ST", "PLACE", "PL") else t
        out.append(t)
    return " ".join(out)


HN = re.compile(r"^\s*(\d+)(?:\s*-\s*(\d+))?\s*([A-Z])?(?:\s*1/2)?")


def house_key(hn: str, boro: int) -> tuple[int, int] | None:
    """-> (sortable key comparable with PAD lhns[1:9], parity number) or None."""
    if not isinstance(hn, str):
        return None
    m = HN.match(hn.upper())
    if not m:
        return None
    a, b = int(m.group(1)), m.group(2)
    if b is not None and boro == 4:  # Queens hyphenated house number 37-04
        return a * 1000 + int(b), int(b)
    return a * 1000, a  # elsewhere "230-240" is a range: use the low number


STREET_TYPES = {"STREET", "ST", "AVENUE", "AVE", "AV", "PLACE", "PL", "ROAD", "RD", "DRIVE", "DR",
                "BOULEVARD", "BLVD", "LANE", "LN", "COURT", "CT", "TERRACE", "TER"}
UNIT = re.compile(r"(\s+-.*$)|(\s*\bAKA.*$)|(\s+(STORE|STORES|STE|SUITE|UNIT|APT|RM|ROOM|SPACE|BSMT|BASEMENT|LOBBY|"
                  r"MEZZ|MEZZANINE|KIOSK|STALL|CONCOURSE|BLDG|BUILDING|AKA|A/K/A|EASTERLY|WESTERLY|NORTHERLY|SOUTHERLY)\b.*$)|(\s*#.*$)|"
                  r"(\s+\d+(ST|ND|RD|TH)?\s+(FL|FLR|FLOOR)\b.*$)|(\s+(FL|FLR|FLOOR)\s*\d*\b.*$)|"
                  r"(\s+(WEST|EAST|NORTH|SOUTH)\s+STORE.*$)")


def clean_street(st: str) -> str:
    return UNIT.sub("", st.upper()).strip() if isinstance(st, str) else ""


def split_address(addr: str) -> tuple[str, str]:
    """'123 1/2 W 4 ST' -> ('123 1/2','W 4 ST'); '34 01 45TH ST' -> ('34-01','45TH ST');
    '242 244 E 79TH ST' -> ('242-244','E 79TH ST') (a range: house_key keeps 242 outside Queens);
    '6801 5 AVENUE' -> ('6801','5 AVENUE')."""
    if not isinstance(addr, str):
        return "", ""
    a = clean_street(re.sub(r"\s+", " ", addr))
    m = re.match(r"^(\d+[A-Z]?(?:\s+1/2)?)((?:\s*-\s*|\s+)\d+[A-Z]?)?(?:\s*-\s*\d+)?\s+(.*)$", a)
    if not m:
        return "", a
    first, second, rest = m.group(1), m.group(2), m.group(3)
    if second:
        nxt = rest.split(" ")[0] if rest else ""
        if nxt in STREET_TYPES or not rest:  # '6801 5 AVENUE': the 2nd number is the street
            return first, f"{second.strip(' -')} {rest}".strip()
        return f"{first}-{second.strip(' -')}", rest
    return first, rest


def build():
    if not PAD_ZIP.exists():
        PAD_ZIP.parent.mkdir(exist_ok=True)
        PAD_ZIP.write_bytes(get(PAD_URL, timeout=900).content)
    z = zipfile.ZipFile(PAD_ZIP)
    snd_name = next(n for n in z.namelist() if n.lower().startswith("snd"))
    rows = []
    for line in io.TextIOWrapper(z.open(snd_name), encoding="latin-1"):
        if line[:1] != "1" or len(line) < 47:
            continue
        rows.append((int(line[1]), line[2:34].strip(), line[37:42]))
    snd = pd.DataFrame(rows, columns=["boro", "name", "sc5"])
    snd["norm"] = snd["name"].map(norm_street)
    snd = snd.drop_duplicates(["boro", "norm", "sc5"])
    save(snd, "snd_streets", source="DCP PAD (bc8t-ecyu)", dataset_id=snd_name,
         note="Street Name Dictionary: every alias name -> 5-digit street code, per borough.")

    usecols = ["boro", "block", "lot", "bin", "lhnd", "lhns", "hhnd", "hhns", "sc5", "stname",
               "addrtype", "parity", "zipcode"]
    pad = pd.read_csv(z.open("bobaadr.txt"), dtype=str, usecols=usecols)
    pad = pad[pad["lhns"].str.strip().str.len() > 0].copy()
    pad["boro"] = pad["boro"].astype(int)
    pad["lkey"] = pd.to_numeric(pad["lhns"].str[1:9], errors="coerce")
    pad["hkey"] = pd.to_numeric(pad["hhns"].str[1:9], errors="coerce")
    pad["bbl"] = pad["boro"].astype(str) + pad["block"].str.zfill(5) + pad["lot"].str.zfill(4)
    pad = pad.dropna(subset=["lkey", "hkey"])
    pad = pad[["boro", "sc5", "lkey", "hkey", "parity", "lhnd", "hhnd", "stname", "addrtype",
               "zipcode", "bbl", "bin"]]
    # condo unit lots -> billing BBL (PLUTO and most city datasets use the billing lot)
    lots = pd.read_csv(z.open("bobabbl.txt"), dtype=str,
                       usecols=["boro", "block", "lot", "billboro", "billblock", "billlot"])
    lots = lots[lots["billlot"].str.strip().fillna("") != ""]
    unit = lots["boro"] + lots["block"].str.zfill(5) + lots["lot"].str.zfill(4)
    bill = lots["billboro"] + lots["billblock"].str.zfill(5) + lots["billlot"].str.zfill(4)
    bmap = dict(zip(unit, bill))
    pad["bbl_billing"] = pad["bbl"].map(bmap).fillna(pad["bbl"])
    print(f"  condo unit lots mapped to billing BBL: {(pad['bbl_billing'] != pad['bbl']).sum():,}")
    save(pad, "pad_addr", source="DCP PAD (bc8t-ecyu)", dataset_id="bobaadr",
         note="PAD address ranges (incl. alias/vanity addresses) -> BBL/BIN. Version in zip.")


class PadGeocoder:
    """address + (borough or ZIP) -> BBL, BIN, lat/lon (PLUTO lot centroid)."""

    def __init__(self):
        snd = pd.read_parquet(OUT / "snd_streets.parquet")
        self.snd = {}
        for b, n, sc in zip(snd["boro"], snd["norm"], snd["sc5"]):
            self.snd.setdefault((b, n), sc)
        pad = pd.read_parquet(OUT / "pad_addr.parquet")
        self.pad = {k: g.reset_index(drop=True) for k, g in pad.groupby(["boro", "sc5"])}
        z = pad.groupby("zipcode")["boro"].agg(lambda s: s.mode().iat[0])
        self.zip_boro = z.to_dict()
        pl = pd.read_parquet(OUT / "pluto_slim.parquet", columns=["bbl", "lat", "lon", "nta2020", "ct2020"])
        self.pluto = pl.set_index("bbl")

    def _streets(self, b: int, street: str):
        """Yield street codes for the name, then for the name + common missing types."""
        n = norm_street(street)
        tried = [n] + [f"{n} {t}" for t in ("STREET", "AVENUE", "PLACE", "ROAD", "BOULEVARD")]
        for cand in tried:
            sc = self.snd.get((b, cand))
            if sc is not None:
                yield sc

    def _houses(self, house: str, b: int):
        keys = [house_key(house, b)]
        m = re.fullmatch(r"\s*(\d{3,5})\s*[A-Z]?\s*", (house or "").upper())
        if b == 4 and m:  # Queens number written without its hyphen: 4512 -> 45-12, 10708 -> 107-08
            d = m.group(1)
            for cut in (len(d) - 2, len(d) - 3):
                if cut >= 1:
                    keys.append(house_key(f"{d[:cut]}-{d[cut:]}", 4))
        return [k for k in keys if k]

    def one(self, house: str, street: str, zip_: str = None, boro=None) -> dict:
        b = BORO.get(str(boro).upper().strip()) if isinstance(boro, str) else None
        z = str(zip_)[:5] if isinstance(zip_, str) and zip_.strip() else None
        if b is None and z:
            b = self.zip_boro.get(z)
        if b is None:
            return {"status": "no_borough"}
        # "212 W" + "79TH ST" -> "212" + "W 79TH ST"
        if isinstance(house, str):
            m = re.fullmatch(r"\s*(.*?\d(?:\s*1/2)?)\s+([NSEW])\s*", house.upper())
            if m:
                house, street = m.group(1), f"{m.group(2)} {street}"
        street = clean_street(street)
        if not self._houses(house, b):
            return {"status": "bad_house_number"}
        zb = self.zip_boro.get(z) if z else None
        # ZIP-only inputs may sit on a borough border; a stated borough can be wrong (Ridgewood
        # "Brooklyn" vs Queens) -> also try the ZIP's borough, then (ZIP-only) all others
        boros = [b] + ([zb] if zb and zb != b else [])
        if boro is None:
            boros += [x for x in (1, 2, 3, 4, 5) if x not in boros]
        found_street = False
        for bb in boros:  # ZIP-only inputs: zip->boro may be ambiguous at borders
            for sc in self._streets(bb, street):
                g = self.pad.get((bb, sc))
                if g is None:
                    continue
                found_street = True
                for key, par in self._houses(house, bb):
                    m = g[(g["lkey"] <= key) & (g["hkey"] >= key)]
                    if len(m) > 1:
                        want = "1" if par % 2 else "2"  # PAD parity: 1 = odd side, 2 = even side
                        m2 = m[(m["parity"] == want) | ~m["parity"].isin(["1", "2"])]
                        m = m2 if len(m2) else m
                        if z is not None and (m["zipcode"] == z).any():
                            m = m[m["zipcode"] == z]
                    if len(m):
                        r = m.iloc[0]
                        out = {"status": "ok", "bbl": r["bbl_billing"], "bbl_lot": r["bbl"],
                               "bin": r["bin"], "pad_street": r["stname"].strip()}
                        if r["bbl_billing"] in self.pluto.index:
                            p = self.pluto.loc[r["bbl_billing"]]
                            out.update(lat=p["lat"], lon=p["lon"], nta2020=p["nta2020"],
                                       ct2020=p["ct2020"])
                        return out
            if found_street:
                return {"status": "house_not_on_street"}
        return {"status": "street_not_found", "norm_street": norm_street(street)}

    def geocode_df(self, df, house, street, zip=None, boro=None) -> pd.DataFrame:
        res = [self.one(h, s, df[zip].iat[i] if zip else None, df[boro].iat[i] if boro else None)
               for i, (h, s) in enumerate(zip_(df[house], df[street]))]
        return pd.DataFrame(res, index=df.index)


zip_ = zip  # geocode_df shadows the builtin name "zip" with its parameter


def geosearch(text: str) -> dict:
    t0 = time.time()
    try:
        r = SESSION.get("https://geosearch.planninglabs.nyc/v2/search",
                        params={"text": text, "size": 1}, timeout=30)
        r.raise_for_status()
        f = r.json().get("features", [])
    except Exception as e:  # recorded per row so the evaluation shows failures
        return {"gs_status": f"error: {e}", "gs_secs": time.time() - t0}
    if not f:
        return {"gs_status": "no_result", "gs_secs": time.time() - t0}
    p = f[0]["properties"]
    lon, lat = f[0]["geometry"]["coordinates"]
    return {"gs_status": "ok", "gs_bbl": p.get("addendum", {}).get("pad", {}).get("bbl"),
            "gs_lat": lat, "gs_lon": lon, "gs_label": p.get("label"),
            "gs_match_type": p.get("match_type"), "gs_conf": p.get("confidence"),
            "gs_layer": p.get("layer"), "gs_secs": time.time() - t0}


def build_sample(n=200, seed=7) -> pd.DataFrame:
    a = pd.read_parquet(OUT / "dcwp_hist_licenses_food.parquet")
    a = pd.DataFrame({"house": a["address_building"], "street": a["address_street_name"],
                      "zip": a["address_zip"], "boro": a["borough"], "bbl": a["bbl"],
                      "lat": a["latitude"], "lon": a["longitude"], "src": "dcwp_hist"})
    o = pd.read_parquet(OUT / "open_restaurants_apps.parquet")
    hs = o["business_address"].str.split(",").str[0].map(split_address)
    o = pd.DataFrame({"house": hs.str[0], "street": hs.str[1], "zip": o["zip"], "boro": o["borough"],
                      "bbl": o["bbl"], "lat": o["latitude"], "lon": o["longitude"], "src": "open_rest"})
    pool = pd.concat([a, o], ignore_index=True).dropna(subset=["bbl", "lat", "house", "street"])
    pool = pool[pool["house"].str.strip() != ""]
    pool["bbl"] = pool["bbl"].str.replace(r"\.0$", "", regex=True)
    full = (pool["house"] + " " + pool["street"]).str.upper()
    strata = {
        "queens_hyphen": pool["house"].str.contains(r"\d-\d") & (pool["bbl"].str[0] == "4"),
        "half_number": full.str.contains("1/2"),
        "ave_of_americas_6av": full.str.contains(r"AMERICAS|\b6(TH)? AV|SIXTH AV"),
        "ordinal_or_abbrev": full.str.contains(r"\b\d+(ST|ND|RD|TH)\b| ST$| AVE?$| PL$"),
        "staten_island": pool["bbl"].str[0] == "5",
        "bronx": pool["bbl"].str[0] == "2",
        "saint_or_named": full.str.contains(r"\bST\.? [A-Z]|BROADWAY|PLAZA|BOULEVARD|BLVD"),
    }
    rng = np.random.default_rng(seed)
    picks, used = [], set()
    quota = {"queens_hyphen": 35, "half_number": 15, "ave_of_americas_6av": 20,
             "ordinal_or_abbrev": 30, "staten_island": 15, "bronx": 15, "saint_or_named": 20}
    for k, q in quota.items():
        idx = [i for i in pool.index[strata[k]] if i not in used]
        sel = rng.choice(idx, size=min(q, len(idx)), replace=False)
        used.update(sel)
        picks.append(pool.loc[sel].assign(stratum=k))
    rest = [i for i in pool.index if i not in used]
    picks.append(pool.loc[rng.choice(rest, size=n - sum(len(p) for p in picks), replace=False)]
                 .assign(stratum="random"))
    s = pd.concat(picks).reset_index(drop=True)
    for c in ("lat", "lon"):
        s[c] = pd.to_numeric(s[c])
    return s


def dist_m(lat1, lon1, lat2, lon2):
    k = math.pi / 180
    x = (lon2 - lon1) * k * np.cos((lat1 + lat2) / 2 * k)
    return np.sqrt(x ** 2 + ((lat2 - lat1) * k) ** 2) * 6_371_000


def evaluate():
    s = build_sample()
    # two input variants: with borough name, and ZIP-only (no borough) like many raw records
    s["text_boro"] = s["house"] + " " + s["street"] + ", " + s["boro"].fillna("") + " NY " + s["zip"].fillna("")
    s["text_zip"] = s["house"] + " " + s["street"] + " " + s["zip"].fillna("")
    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        gb = list(ex.map(geosearch, s["text_boro"]))
        gz = list(ex.map(geosearch, s["text_zip"]))
    gs_secs = time.time() - t0
    gb = pd.DataFrame(gb).add_suffix("_boro")
    gz = pd.DataFrame(gz).add_suffix("_zip")
    g = PadGeocoder()
    t1 = time.time()
    lb = g.geocode_df(s, "house", "street", zip="zip", boro="boro").add_prefix("pad_").add_suffix("_boro")
    lz = g.geocode_df(s, "house", "street", zip="zip").add_prefix("pad_").add_suffix("_zip")
    pad_secs = time.time() - t1
    e = pd.concat([s, gb, gz, lb, lz], axis=1)
    summary = {}
    for v in ("boro", "zip"):
        bblcol, lat, lon = f"gs_bbl_{v}", f"gs_lat_{v}", f"gs_lon_{v}"
        e[f"gs_bbl_ok_{v}"] = e[bblcol] == e["bbl"]
        e[f"gs_dist_{v}"] = dist_m(e["lat"], e["lon"], e[lat], e[lon])
        e[f"gs_hit_{v}"] = e[f"gs_bbl_ok_{v}"] | (e[f"gs_dist_{v}"] < 100)
        e[f"gs_exact_{v}"] = e[f"gs_match_type_{v}"] == "exact"
        e[f"pad_bbl_ok_{v}"] = e[f"pad_bbl_{v}"] == e["bbl"]
        e[f"pad_dist_{v}"] = dist_m(e["lat"], e["lon"], e[f"pad_lat_{v}"], e[f"pad_lon_{v}"])
        e[f"pad_hit_{v}"] = e[f"pad_bbl_ok_{v}"] | (e[f"pad_dist_{v}"] < 100)
        summary[v] = {
            "gs_returned": float((e[f"gs_status_{v}"] == "ok").mean()),
            "gs_bbl_exact": float(e[f"gs_bbl_ok_{v}"].mean()),
            "gs_hit_bbl_or_100m": float(e[f"gs_hit_{v}"].mean()),
            "gs_wrong_but_confident": float(((e[f"gs_status_{v}"] == "ok") & ~e[f"gs_hit_{v}"]).mean()),
            "pad_returned": float((e[f"pad_status_{v}"] == "ok").mean()),
            "pad_bbl_exact": float(e[f"pad_bbl_ok_{v}"].mean()),
            "pad_hit_bbl_or_100m": float(e[f"pad_hit_{v}"].mean()),
            "pad_wrong": float(((e[f"pad_status_{v}"] == "ok") & ~e[f"pad_hit_{v}"]).mean()),
            "combined_pad_then_gs": float((e[f"pad_hit_{v}"] | ((e[f"pad_status_{v}"] != "ok") & e[f"gs_hit_{v}"])).mean()),
        }
    by = e.groupby("stratum")[["gs_hit_boro", "gs_hit_zip", "pad_hit_boro", "pad_hit_zip"]].mean().round(2)
    e = e.drop(columns=[c for c in e.columns if e[c].dtype == object and c.endswith("_label_zip")])
    save(e, "geocode_eval", source="evaluation", dataset_id="geosearch+pad",
         note=f"200-address eval. geosearch {2*len(s)} calls in {gs_secs:.0f}s with 8 threads; "
              f"PAD local {2*len(s)} in {pad_secs:.1f}s")
    print(pd.DataFrame(summary).round(3).to_string())
    print(by.to_string())
    print(f"geosearch: {2*len(s)/gs_secs:.1f} req/s (8 threads); median latency "
          f"{pd.concat([gb['gs_secs_boro'], gz['gs_secs_zip']]).median():.2f}s; PAD {2*len(s)/pad_secs:.0f}/s")
    print(e.loc[~e["pad_hit_boro"], ["stratum", "house", "street", "boro", "zip", "bbl",
                                     "pad_status_boro", "pad_bbl_boro", "gs_bbl_boro"]].to_string())


if __name__ == "__main__":
    {"build": build, "eval": evaluate}[sys.argv[1]]()
