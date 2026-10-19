"""Compare our inventory (DOHMH CAMIS union + SLA bars) with CBP/ZBP/QCEW counts and BDS/BED exit rates.

Writes to data/raw/benchmarks/:
  compare_borough_year.csv   coverage ratios by year x borough (+ NYC)
  compare_zip_year.parquet   DOHMH active vs ZBP establishments by ZIP x year
  zip_shortfalls.csv         ZIPs / ZIP-years with the largest shortfalls
  closure_rates.csv          our implied exit/entry rates vs BDS (sector 72, NAICS 7225) and BED
"""
import re

import duckdb
import numpy as np
import pandas as pd

from bench_common import NYC_COUNTIES, OUT, ROOT, log, zip_to_boro

UNION = ROOT / "data" / "raw" / "dohmh" / "union_inspections.parquet"
MANIFEST = ROOT / "data" / "raw" / "dohmh" / "manifest.csv"
SLA = ROOT / "data" / "raw" / "gov" / "sla_licenses_nyc.parquet"
YEARS = range(2012, 2026)
BOROS = ["Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"]
BORO_NORM = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island",
             "MANHATTAN": "Manhattan", "BRONX": "Bronx", "BROOKLYN": "Brooklyn", "QUEENS": "Queens",
             "STATEN ISLAND": "Staten Island"}
SLA_CTY = {"NEW": "Manhattan", "NEW YORK": "Manhattan", "KING": "Brooklyn", "KINGS": "Brooklyn",
           "QUEE": "Queens", "QUEENS": "Queens", "BRON": "Bronx", "BRONX": "Bronx",
           "RICH": "Staten Island", "RICHMOND": "Staten Island"}


def _norm(s):
    return s.fillna("").str.upper().map(lambda x: re.sub(r"[^A-Z0-9]", "", x))


def load_camis():
    """One row per CAMIS: start (first real inspection or first snapshot), end (last snapshot seen)."""
    con = duckdb.connect()
    df = con.sql(f"""
        with u as (select * from '{UNION}'),
        agg as (
          select camis,
                 min(case when inspection_date > date '1901-01-01' then inspection_date end) first_insp,
                 min(first_snapshot) first_seen, max(last_snapshot) last_seen
          from u group by camis),
        latest as (
          select camis, arg_max(boro, coalesce(inspection_date, last_snapshot)) boro,
                 arg_max(zipcode, coalesce(inspection_date, last_snapshot)) zipcode,
                 arg_max(dba, coalesce(inspection_date, last_snapshot)) dba,
                 arg_max(building, coalesce(inspection_date, last_snapshot)) building
          from u where zipcode is not null or boro is not null group by camis)
        select agg.*, latest.boro, latest.zipcode, latest.dba, latest.building
        from agg left join latest using (camis)""").df()
    df["zip"] = df.zipcode.astype(str).str.extract(r"^(\d{5})")[0]
    b = df.boro.astype(str).str.strip().str.upper().map(BORO_NORM)
    df["borough"] = b.fillna(df.zip.map(zip_to_boro))
    df["start"] = pd.to_datetime(df[["first_insp", "first_seen"]].min(axis=1))
    df["end"] = pd.to_datetime(df.last_seen)
    df["censored"] = df.end >= df.end.max()  # still in the latest pull
    # The closure happened between the last sighting and the next full copy (PARTIAL/DERIVED copies
    # are presence evidence only, dohmh_gaps.md). Date it at the midpoint: `end_mid`.
    man = pd.read_csv(MANIFEST, usecols=["snapshot_date", "notes"])
    full = man[~man.notes.fillna("").str.match(r"^(PARTIAL|DERIVED)")]
    full = pd.Series(sorted(pd.to_datetime(full.snapshot_date).dropna().unique()))
    nxt = full.searchsorted(df.end.values, side="right")
    nxt_date = pd.Series(full.reindex(nxt).values, index=df.index)
    df["end_mid"] = (df.end + (nxt_date - df.end) / 2).where(~df.censored, df.end)
    df["end_mid"] = df.end_mid.fillna(df.end)
    df["synthetic"] = df.camis.str.startswith("X")
    # Re-permit: same name + building + ZIP gets another CAMIS starting within ~400 days of this
    # one's last sighting -> ownership/permit change, not a closure (crosscheck.md: ~21% of drops).
    df["key"] = _norm(df.dba) + "|" + _norm(df.building) + "|" + df.zip.fillna("")
    k = df[df.dba.notna() & df.zip.notna()][["camis", "key", "start", "end"]]
    m = k.merge(k, on="key", suffixes=("", "_n"))
    m = m[(m.camis != m.camis_n) & (m.start_n > m.start) &
          ((m.start_n - m.end).dt.days.abs() <= 400)]
    df["repermit"] = df.camis.isin(m.camis)
    log(f"CAMIS {len(df)} (synthetic {df.synthetic.sum()}), no borough {df.borough.isna().sum()}, "
        f"re-permits {df.repermit.sum()}, latest pull {df.end.max().date()}")
    return df


def active_counts(df, by):
    rows = []
    for y in YEARS:
        ys, ye, ref = pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31), pd.Timestamp(y, 3, 12)
        a = df[(df.start <= ye) & (df.end >= ys)]
        pt = df[(df.start <= ref) & (df.end_mid >= ref)]  # point stock on the CBP reference date
        g = a.groupby(by).agg(active=("camis", "size"), synthetic=("synthetic", "sum"))
        g["active_real"] = g.active - g.synthetic
        g["stock_mar12"] = pt[~pt.synthetic].groupby(by).size()
        rows.append(g.reset_index().assign(year=y))
    return pd.concat(rows, ignore_index=True)


def sla_bars():
    s = pd.read_parquet(SLA, columns=["county", "category", "start_date", "end_date", "premise_key"])
    s = s[s.category.eq("bar_tavern")]
    s["borough"] = s.county.str.upper().map(SLA_CTY)
    p = s.groupby(["premise_key", "borough"]).agg(start=("start_date", "min"), end=("end_date", "max"),
                                                 open_now=("end_date", lambda x: x.isna().any())).reset_index()
    p.loc[p.open_now, "end"] = pd.Timestamp.max
    rows = []
    for y in YEARS:
        a = p[(p.start <= pd.Timestamp(y, 12, 31)) & (p.end >= pd.Timestamp(y, 1, 1))]
        rows.append(a.groupby("borough").size().rename("sla_bars").reset_index().assign(year=y))
    return pd.concat(rows, ignore_index=True)


def cbp_counts():
    c = pd.read_parquet(OUT / "cbp_county_nyc.parquet")
    piv = c.pivot_table(index=["year", "borough"], columns="naics", values="est", aggfunc="sum").fillna(0)
    out = pd.DataFrame(index=piv.index)
    out["cbp_rest"] = np.where(piv.index.get_level_values(0) >= 2012, piv.get("7225", 0),
                               piv.get("7221", 0) + piv.get("7222", 0))
    out["cbp_bars"] = piv["7224"]
    out["cbp_722"] = piv["722"]
    return out.reset_index()


def qcew_counts():
    q = pd.read_parquet(OUT / "qcew_nyc_quarterly.parquet")
    q = q[(q.own_code == "5") & q.industry_code.isin(["7225", "7224"])]
    a = q.groupby(["year", "borough", "industry_code"]).qtrly_estabs.mean().unstack()
    return a.rename(columns={"7225": "qcew_rest", "7224": "qcew_bars"}).reset_index()


def zbp_counts():
    z = pd.read_parquet(OUT / "zbp_detail_nyc.parquet")
    z = z[z.naics.isin(["7225", "7221", "7222", "7224", "722"])]
    piv = z.pivot_table(index=["year", "zip"], columns="naics", values="est", aggfunc="sum").fillna(0)
    rest = np.where(piv.index.get_level_values(0) >= 2012, piv.get("7225", 0),
                    piv.get("7221", 0) + piv.get("7222", 0))
    out = pd.DataFrame({"zbp_rest_bars": rest + piv.get("7224", 0), "zbp_722": piv.get("722", 0)},
                       index=piv.index).reset_index()
    boro = z.drop_duplicates("zip").set_index("zip").borough
    out["borough"] = out.zip.map(boro)
    return out


def rates(df):
    """Exit = closure (end_mid) in year Y and absent from the latest pull. Denominator = mean of
    Jan-1 stocks of Y and Y+1 (BDS uses the mean of the March-12 counts of t-1 and t)."""
    d = df[~df.synthetic & df.borough.notna()]
    rows = []
    for y in YEARS:
        s0 = (d.start < pd.Timestamp(y, 1, 1)) & (d.end_mid >= pd.Timestamp(y, 1, 1))
        s1 = (d.start < pd.Timestamp(y + 1, 1, 1)) & (d.end_mid >= pd.Timestamp(y + 1, 1, 1))
        ex = (~d.censored) & (d.end_mid.dt.year == y)
        en = d.start.dt.year == y
        for b, g in [("NYC", d.index)] + [(b, d.index[d.borough == b]) for b in BOROS]:
            den = (s0[g].sum() + s1[g].sum()) / 2
            rows.append({"year": y, "borough": b, "denom": den,
                         "exits": int(ex[g].sum()), "exits_excl_repermit": int((ex & ~d.repermit)[g].sum()),
                         "entries": int(en[g].sum())})
    r = pd.DataFrame(rows)
    r["exit_rate"] = 100 * r.exits / r.denom
    r["exit_rate_adj"] = 100 * r.exits_excl_repermit / r.denom
    r["entry_rate"] = 100 * r.entries / r.denom
    # official
    bc = pd.read_parquet(OUT / "bds_st_cty_sec.parquet")
    bc["borough"] = bc.cty.map(NYC_COUNTIES)
    bds = bc[["year", "borough", "estabs_exit_rate", "estabs_entry_rate"]].copy()
    # NYC = 5 counties pooled; each county's rate denominator is recovered as count*100/rate.
    num = bc.assign(**{c: pd.to_numeric(bc[c], errors="coerce") for c in
                       ["estabs_exit", "estabs_exit_rate", "estabs_entry", "estabs_entry_rate"]})
    num["den"] = num.estabs_exit * 100 / num.estabs_exit_rate
    g = num.groupby("year")[["estabs_exit", "estabs_entry", "den"]].sum()
    bds = pd.concat([bds, pd.DataFrame({"year": g.index, "borough": "NYC",
                                        "estabs_exit_rate": 100 * g.estabs_exit / g.den,
                                        "estabs_entry_rate": 100 * g.estabs_entry / g.den})])
    v4 = pd.read_parquet(OUT / "bds_vcn4.parquet")
    v4 = v4[v4.vcnaics4 == "7225"][["year", "estabs_exit_rate", "estabs_entry_rate"]]
    msa = pd.read_parquet(OUT / "bds_msa_sec.parquet")[["year", "estabs_exit_rate", "estabs_entry_rate"]]
    for t in (bds, v4, msa):
        for c in ("estabs_exit_rate", "estabs_entry_rate"):
            t[c] = pd.to_numeric(t[c], errors="coerce")
    r = r.merge(bds.rename(columns={"estabs_exit_rate": "bds72_cty_exit", "estabs_entry_rate": "bds72_cty_entry"}),
                on=["year", "borough"], how="left")
    r = r.merge(msa.rename(columns={"estabs_exit_rate": "bds72_nyc_msa_exit", "estabs_entry_rate": "bds72_nyc_msa_entry"}),
                on="year", how="left")
    r = r.merge(v4.rename(columns={"estabs_exit_rate": "bds7225_us_exit", "estabs_entry_rate": "bds7225_us_entry"}),
                on="year", how="left")
    bed = pd.read_parquet(OUT / "bed_openings_closings.parquet")
    bed = bed[(bed.kind == "rate") & bed.series.str.startswith("US NAICS 722")]
    bed = bed.pivot_table(index="year", columns="event", values="value", aggfunc="sum")
    bed.columns = [f"bed722_us_{c}_sum4q" for c in bed.columns]
    r = r.merge(bed.reset_index(), on="year", how="left")
    return r


def main():
    df = load_camis()
    act_b = active_counts(df[df.borough.notna()], "borough")
    nyc = act_b.groupby("year")[["active", "synthetic", "active_real", "stock_mar12"]].sum().reset_index()
    act_b = pd.concat([act_b, nyc.assign(borough="NYC")], ignore_index=True)
    bench = cbp_counts().merge(qcew_counts(), on=["year", "borough"], how="outer")
    bench = pd.concat([bench, bench.groupby("year").sum(numeric_only=True, min_count=1).reset_index().assign(borough="NYC")])
    bars = sla_bars()
    bars = pd.concat([bars, bars.groupby("year").sla_bars.sum().reset_index().assign(borough="NYC")])
    cmp_ = act_b.merge(bench, on=["year", "borough"], how="left").merge(bars, on=["year", "borough"], how="left")
    cmp_["cov_cbp"] = cmp_.active_real / (cmp_.cbp_rest + cmp_.cbp_bars)
    cmp_["cov_cbp_pt"] = cmp_.stock_mar12 / (cmp_.cbp_rest + cmp_.cbp_bars)
    cmp_["cov_qcew"] = cmp_.active_real / (cmp_.qcew_rest + cmp_.qcew_bars)
    cmp_["sla_bars_vs_cbp7224"] = cmp_.sla_bars / cmp_.cbp_bars
    cmp_.sort_values(["borough", "year"]).to_csv(OUT / "compare_borough_year.csv", index=False)

    # ZIP level
    act_z = active_counts(df[df.zip.notna() & ~df.synthetic], "zip")
    z = zbp_counts().merge(act_z[["year", "zip", "active_real", "stock_mar12"]], on=["year", "zip"], how="left")
    z["active_real"] = z.active_real.fillna(0)
    z["ratio"] = z.active_real / z.zbp_rest_bars.where(z.zbp_rest_bars > 0)
    z["shortfall"] = z.zbp_rest_bars - z.active_real
    z.to_parquet(OUT / "compare_zip_year.parquet", index=False)
    # DOHMH runs ~1.35x CBP citywide, so a raw ZBP-minus-DOHMH shortfall is almost never positive.
    # Expected DOHMH = ZBP x that year's borough ratio; residual = DOHMH - expected.
    z = z[z.year >= 2012]
    tot = z.groupby(["year", "borough"])[["active_real", "zbp_rest_bars"]].transform("sum")
    z["expected"] = z.zbp_rest_bars * tot.active_real / tot.zbp_rest_bars
    z["resid"] = z.active_real - z.expected
    z["rel_cov"] = z.active_real / z.expected.where(z.expected > 0)
    big = z[z.zbp_rest_bars >= 10].copy()
    persist = big.groupby(["zip", "borough"]).agg(
        years=("year", "nunique"), zbp_mean=("zbp_rest_bars", "mean"), dohmh_mean=("active_real", "mean"),
        raw_ratio=("ratio", "median"), rel_cov=("rel_cov", "median"), resid_mean=("resid", "mean")).reset_index()
    persist = persist.sort_values("resid_mean")
    big["zip_med_rel"] = big.groupby("zip").rel_cov.transform("median")
    big["dip"] = big.rel_cov / big.zip_med_rel
    yr = big[(big.dip < 0.8) & (big.zbp_rest_bars >= 20)].sort_values("dip")
    nodohmh = z[(z.active_real == 0) & (z.zbp_rest_bars >= 5)].groupby("zip").agg(
        years=("year", "nunique"), zbp_mean=("zbp_rest_bars", "mean")).sort_values("zbp_mean", ascending=False)
    with open(OUT / "zip_shortfalls.csv", "w") as f:
        f.write("# A: ZIPs ranked by mean residual (DOHMH active minus ZBP 7225+7224 x borough-year ratio); ZBP>=10\n")
        persist.head(60).round(3).to_csv(f, index=False)
        f.write("\n# B: ZIP-years whose relative coverage is <0.8x the ZIP's own median (possible missing year); ZBP>=20\n")
        yr[["year", "zip", "borough", "zbp_rest_bars", "active_real", "rel_cov", "zip_med_rel", "dip"]].round(3).to_csv(f, index=False)
        f.write("\n# C: ZIPs with ZBP restaurants/bars but zero DOHMH CAMIS (mostly building/PO-box ZIPs)\n")
        nodohmh.round(1).to_csv(f)
    r = rates(df)
    r.to_csv(OUT / "closure_rates.csv", index=False)
    log("wrote compare_borough_year.csv, compare_zip_year.parquet, zip_shortfalls.csv, closure_rates.csv")
    return cmp_, z, persist, yr, r


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    cmp_, z, persist, yr, r = main()
    print(cmp_.pivot(index="year", columns="borough", values="cov_cbp").round(2))
    print(cmp_.pivot(index="year", columns="borough", values="cov_qcew").round(2))
    print(cmp_[cmp_.borough == "NYC"][["year", "active_real", "stock_mar12", "cbp_rest", "cbp_bars", "qcew_rest",
                                       "qcew_bars", "sla_bars", "cov_cbp", "cov_cbp_pt", "cov_qcew"]].round(2).to_string())
    print(persist.head(15).round(2).to_string())
    print(yr.head(20).round(2).to_string())
    print(z[z.rel_cov.notna()].groupby("year").apply(lambda g: (g.rel_cov < 0.8).sum()))
    print(r[r.borough == "NYC"].drop(columns=["borough"]).round(1).to_string())
