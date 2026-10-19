"""Build data/raw/traffic/traffic_by_tract_year.parquet (2020 tracts x 2011-2025) and the
lot-level helper table data/raw/traffic/subway_access_lot.parquet. Definitions: data/notes/traffic.md.

Location kernels (subway, Citi Bike) are evaluated at every PLUTO lot and averaged over the
lots in a tract (tracts without lots use their representative point), so large tracts are not
judged from one centroid.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from traffic_access import kernel_pairs, kernel_sum, xy_m
from traffic_common import GOV, METRIC_CRS, OUT, YEARS, save, tracts

AIRPORT_ZONES = {1, 132, 138}  # EWR, JFK, LaGuardia: air travel, not street activity
COMPONENTS = {"subway_entries_w400": "z_subway", "tlc_dropoffs_km2": "z_tlc",
              "jobs_km2": "z_jobs", "residents_km2": "z_residents"}
BASE_YEAR = 2019


def _points(t) -> pd.DataFrame:
    lots = pd.read_parquet(GOV / "pluto_slim.parquet", columns=["bbl", "lat", "lon", "bct2020"])
    lots = lots.dropna(subset=["lat", "lon", "bct2020"])
    lots = lots.merge(t[["boroct2020", "geoid"]], left_on="bct2020", right_on="boroct2020")
    rp = t[~t.geoid.isin(lots.geoid)].copy()
    rp["pt"] = rp.geometry.representative_point()
    extra = pd.DataFrame({"bbl": None, "lat": rp.pt.y, "lon": rp.pt.x, "geoid": rp.geoid})
    return pd.concat([lots[["bbl", "lat", "lon", "geoid"]], extra], ignore_index=True)


def _subway(pts, P) -> pd.DataFrame:
    st = pd.read_parquet(OUT / "subway_station_year.parquet")
    loc = st.drop_duplicates("complex_id")[["complex_id", "station", "lat", "lon"]].reset_index(drop=True)
    S = xy_m(loc.lat, loc.lon)
    i, j, w = kernel_pairs(P, S)
    frames = []
    for y in YEARS:
        s = st[st.year == y].set_index("complex_id")
        e = s.entries.reindex(loc.complex_id).fillna(0).to_numpy()
        ev = (s.entries * s.wkdy_eve_share).reindex(loc.complex_id).fillna(0).to_numpy()
        frames.append(pd.DataFrame({
            "geoid": pts.geoid, "year": y,
            "subway_entries_w400": np.bincount(i, w * e[j], minlength=len(P)),
            "subway_eve_entries_w400": np.bincount(i, w * ev[j], minlength=len(P))}))
    out = pd.concat(frames).groupby(["geoid", "year"], as_index=False).mean()
    # static lot helper: nearest complex + distance
    from scipy.spatial import cKDTree
    d, k = cKDTree(S).query(P)
    lot = pd.DataFrame({"bbl": pts.bbl, "geoid": pts.geoid, "nearest_complex_id": loc.complex_id[k].values,
                        "nearest_station": loc.station[k].values, "nearest_m": d.round(1)})
    near = lot.groupby("geoid").nearest_m.mean().rename("subway_nearest_m_mean")
    save(lot.dropna(subset=["bbl"]), "subway_access_lot", source="PLUTO lots x MTA complexes",
         note="nearest subway complex per BBL; join subway_station_year for entries by year")
    return out.merge(near, on="geoid")


def _citibike(pts, P) -> pd.DataFrame:
    cb = pd.read_parquet(OUT / "citibike_station_year.parquet")
    frames = []
    for y in YEARS:
        s = cb[cb.year == y]
        v = (kernel_sum(P, xy_m(s.lat, s.lon), s.annualized_trips.to_numpy())
             if len(s) else np.zeros(len(P)))
        frames.append(pd.DataFrame({"geoid": pts.geoid, "year": y, "citibike_trips_w400": v}))
    return pd.concat(frames).groupby(["geoid", "year"], as_index=False).mean()


def _tlc() -> pd.DataFrame:
    z = pd.read_parquet(OUT / "tlc_zone_year.parquet")
    z = z[~z.zone.isin(AIRPORT_ZONES)].copy()  # dropoffs are already annual estimates
    z["taxi"] = z.dropoffs.where(z.service.isin(["yellow", "green"]), 0)
    z["hourly"] = z.dropoffs.where(z.do_night.notna(), 0)
    cols = ["dropoffs", "taxi", "hourly", "do_night", "do_wkdy_eve"]
    zy = z.groupby(["zone", "year"])[cols].sum().reset_index()
    w = pd.read_parquet(OUT / "tlc_zone_tract_weights.parquet")
    m = zy.merge(w, left_on="zone", right_on="zone_id")
    for c in cols:
        m[c] = m[c] * m.w
    t = m.groupby(["geoid", "year"])[cols].sum().reset_index().rename(columns={
        "dropoffs": "tlc_dropoffs", "taxi": "tlc_taxi_dropoffs", "hourly": "tlc_dropoffs_hourly"})
    # shares only cover services with hourly data (yellow; FHV 2015-18), see tlc_zone_year
    t["tlc_night_share"] = t.do_night / t.tlc_dropoffs_hourly
    t["tlc_wkdy_eve_share"] = t.do_wkdy_eve / t.tlc_dropoffs_hourly
    return t.drop(columns=["do_night", "do_wkdy_eve", "tlc_dropoffs_hourly"])


def _carry(df: pd.DataFrame, cols: list[str], tag: str) -> pd.DataFrame:
    """Fill panel years after the last published year with the last value; record year used."""
    last = int(df.year.max())
    df = df.assign(**{tag: df.year})
    extra = [df[df.year == last].assign(year=y) for y in YEARS if y > last]
    return pd.concat([df, *extra], ignore_index=True)[["geoid", "year", tag, *cols]]


def run() -> pd.DataFrame:
    t = tracts()
    tm = t.to_crs(METRIC_CRS)
    area = pd.Series(tm.geometry.area.to_numpy() * 0.09290304 / 1e6, index=t.geoid, name="area_km2")
    pts = _points(t)
    P = xy_m(pts.lat, pts.lon)
    print(f"  {len(pts):,} points ({pts.bbl.isna().sum()} tract representative points)", flush=True)

    panel = pd.MultiIndex.from_product([t.geoid, YEARS], names=["geoid", "year"]).to_frame(index=False)
    panel = panel.merge(t[["geoid", "boroct2020", "nta2020", "ntaname"]], on="geoid")
    panel["area_km2"] = panel.geoid.map(area)
    lodes = pd.read_parquet(OUT / "lodes_wac_tract_year.parquet")
    acs = pd.read_parquet(OUT / "acs_pop_tract_year.parquet").rename(columns={"pop": "residents"})
    for part in (_subway(pts, P), _tlc(), _citibike(pts, P),
                 _carry(lodes, ["jobs", "jobs_food_accom", "jobs_retail"], "jobs_year_used"),
                 _carry(acs, ["residents"], "residents_year_used")):
        panel = panel.merge(part, on=["geoid", "year"], how="left")
    fill0 = ["tlc_dropoffs", "tlc_taxi_dropoffs", "citibike_trips_w400", "jobs", "jobs_food_accom",
             "jobs_retail", "residents"]
    panel[fill0] = panel[fill0].fillna(0)
    panel["tlc_dropoffs_km2"] = panel.tlc_dropoffs / panel.area_km2
    panel["jobs_km2"] = panel.jobs / panel.area_km2
    panel["residents_km2"] = panel.residents / panel.area_km2

    # composite: log1p each component, z-score against the pooled 2019 tract distribution
    for c, zc in COMPONENTS.items():
        lx = np.log1p(panel[c])
        base = lx[panel.year == BASE_YEAR]
        panel[zc] = (lx - base.mean()) / base.std()
        g = lx.groupby(panel.year)
        panel[zc + "_wy"] = (lx - g.transform("mean")) / g.transform("std")
    zs = list(COMPONENTS.values())
    panel["fti"] = panel[zs].mean(axis=1)
    panel["fti_within_year"] = panel[[z + "_wy" for z in zs]].mean(axis=1)
    panel = panel.drop(columns=[z + "_wy" for z in zs])
    panel["fti_pctile"] = panel.groupby("year").fti.rank(pct=True)
    save(panel, "traffic_by_tract_year", source="derived: subway, TLC, LODES, ACS, Citi Bike",
         note=f"fti = mean of z(log1p) of {list(COMPONENTS)}; z vs {BASE_YEAR} tract distribution")
    return panel


if __name__ == "__main__":
    run()
