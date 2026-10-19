"""Station complexes (coordinates) and the turnstile remote-unit -> station-complex crosswalk.

The MetroCard history and turnstile files identify stations by remote unit (R001...) with
abbreviated names ("JKSN HT-ROOSVLT") and route strings ("EFMR7"); the hourly ridership uses
station complex ids. No official crosswalk is published on data.ny.gov, so units are matched
to complexes by route overlap + fuzzy name similarity + division, using unit lists from the
2014/2016/2019 turnstile datasets. Output: data/raw/traffic/subway_remote_complex_map.parquet
(remote, ts_station, line_name, complex_id, complex_name, score, route_overlap, name_sim).
Quality check: traffic_subway.py compares mapped MetroCard swipes with hourly ridership in 2017-18.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

from traffic_common import save, soql

D = "data.ny.gov"
TURNSTILE = {2014: ("i55r-43gk", "linename"), 2016: ("ekwu-khcy", "line_name"),
             2019: ("xfn5-qji9", "line_name")}
ABBR = {"ST": "ST", "STREET": "ST", "AVE": "AV", "AV": "AV", "AVENUE": "AV", "SQ": "SQ",
        "HTS": "HTS", "HT": "HTS", "JKSN": "JACKSON", "ROOSVLT": "ROOSEVELT", "PK": "PARK",
        "BLVD": "BLVD", "STA": "STATION", "CTR": "CENTER", "CNTR": "CENTER", "RD": "RD",
        "PKWY": "PKWY", "PL": "PL", "HWY": "HWY", "TERM": "TERMINAL", "BCH": "BEACH",
        "JCT": "JUNCTION", "BKLYN": "BROOKLYN", "BRDWY": "BROADWAY", "BWAY": "BROADWAY",
        "GRD": "GRAND", "CNTRL": "CENTRAL", "LEX": "LEXINGTON", "UNION": "UNION", "WTC": "WTC"}


def complexes() -> pd.DataFrame:
    """Complex id, display name, borough, lat/lon, routes, member stop names."""
    c = soql(D, "5f5g-n3cz", select="complex_id, display_name, borough, latitude, longitude, "
             "daytime_routes, constituent_station_names, structure_type")
    c = c.rename(columns={"display_name": "station", "latitude": "lat", "longitude": "lon"})
    c["lat"], c["lon"] = c.lat.astype(float), c.lon.astype(float)
    # Roosevelt Island Tramway appears in the hourly data but not in the complex list
    tram = pd.DataFrame({"complex_id": ["TRAM1", "TRAM2"],
                         "station": ["RI Tramway (Manhattan)", "RI Tramway (Roosevelt)"],
                         "borough": ["M", "M"], "lat": [40.761337, 40.75734],
                         "lon": [-73.96416, -73.95412], "daytime_routes": ["", ""],
                         "constituent_station_names": ["", ""], "structure_type": ["Tram"] * 2})
    return pd.concat([c, tram], ignore_index=True)


def _norm(s: str) -> str:
    toks = re.split(r"[^A-Z0-9]+", str(s).upper())
    toks = [re.sub(r"^(\d+)(ST|ND|RD|TH)$", r"\1", t) for t in toks if t]
    return " ".join(ABBR.get(t, t) for t in toks)


def _routes(s: str, division: str = "") -> set:
    """Turnstile line_name 'NQR456W' -> {'N','Q','R','4','5','6'}; GTFS 'N Q R W' -> tokens."""
    if division == "SRT":
        return {"SIR"}
    s = str(s).upper()
    toks = set(s.split()) if " " in s or s == "SIR" else set(s)
    return toks - {"W"} if len(toks) > 1 else toks  # W ran only part of 2010-16; weak signal


# hand-checked: routes changed since (F->M on 63 St line) or names too abbreviated; None = not a
# subway station (airport/bus/tourist-booth MetroCard units)
OVERRIDE = {"R303": "221", "R259": "222", "R095": "1", "R083": "14", "R081": "10",
            "R468": "TRAM1", "R469": "TRAM2",
            "R536": None, "R537": None, "R538": None, "R410": None, "R459": None, "R526": None}

GENERIC = {"ST", "AV", "RD", "BLVD", "PL", "PKWY", "SQ", "STATION", "HTS", "PARK", "AND", "N", "S",
           "E", "W"}


def _name_sim(a: str, b: str) -> float:
    seq = SequenceMatcher(None, a, b).ratio()
    ta = [t for t in a.split() if t not in GENERIC and not t.isdigit()]
    tb = [t for t in b.split() if t not in GENERIC and not t.isdigit()]
    if not ta:
        return seq
    hit = sum(any(x.startswith(y) or y.startswith(x) for y in tb if min(len(x), len(y)) >= 3)
              for x in ta)
    return max(seq, hit / len(ta))


def remote_to_complex(cx: pd.DataFrame) -> pd.DataFrame:
    units = pd.concat([soql(D, ds, select=f"unit, station, {ln} as line_name, division, count(*) as n",
                            group=f"unit, station, {ln}, division", order="unit")
                       for ds, ln in TURNSTILE.values()])
    units = units[units.division != "PTH"]  # PATH
    units["n"] = units.n.astype(int)
    st = soql(D, "39hk-dx4f", select="complex_id, stop_name, daytime_routes, division")
    grp = st.groupby("complex_id").agg(
        names=("stop_name", lambda x: [_norm(v) for v in set(x)]),
        routes=("daytime_routes", lambda x: set().union(*[_routes(v) for v in x])),
        divs=("division", set)).reset_index()
    grp = grp.merge(cx[["complex_id", "station"]], on="complex_id", how="left")

    rows = []
    for unit, g in units.groupby("unit"):
        top = g.sort_values("n", ascending=False).iloc[0]
        r_u = set().union(*[_routes(x, d) for x, d in zip(g.line_name, g.division)])
        n_u = _norm(top.station)
        nums_u = set(re.findall(r"\d+", n_u))
        best = None
        for c in grp.itertuples():
            ro = len(r_u & c.routes) / max(len(r_u), len(c.routes), 1)
            ns = max(_name_sim(n_u, n) for n in c.names)
            nums_c = set().union(*[set(re.findall(r"\d+", n)) for n in c.names])
            miss = len(nums_u - nums_c) / len(nums_u) if nums_u else 0.0
            num = -0.4 * miss + (0.1 if nums_u and miss == 0 else 0.0)
            score = 0.55 * ns + 0.35 * ro + 0.1 * (top.division in c.divs) + num
            if best is None or score > best[0]:
                best = (score, c.complex_id, c.station, ro, ns)
        rows.append((unit, top.station, top.line_name, best[1], best[2], best[0], best[3],
                     best[4]))
    out = pd.DataFrame(rows, columns=["remote", "ts_station", "line_name", "complex_id",
                                      "complex_name", "score", "route_overlap", "name_sim"])
    weak = out[out.score < 0.5]
    print(f"  remote map: {len(out)} units, {out.complex_id.notna().sum()} mapped, "
          f"{len(weak)} weak (score<0.5)", flush=True)
    for remote, cid in OVERRIDE.items():
        out.loc[out.remote == remote, ["complex_id", "score"]] = [cid, 1.0]
    out.loc[out.score < 0.4, "complex_id"] = None  # too uncertain: leave unmapped
    save(out, "subway_remote_complex_map", source="data.ny.gov turnstile unit lists + 39hk-dx4f",
         note="fuzzy route+name match; score<0.4 left unmapped")
    return out
