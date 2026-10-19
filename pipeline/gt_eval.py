"""Accuracy of DOHMH-inferred opening / closing dates against dated blog / Eater / Grub Street posts.

Closures: post date d vs business window [L, U] (L = last inspection, U = first full copy
without it). Openings: d vs F (first inspection). One record per (business, event): the
earliest post. Writes eval_closures.parquet, eval_openings.parquet and summary.json.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from gt_common import OUT

GAPS = {"2015-03..08": ("2015-03-01", "2015-08-02"), "2016-04..12": ("2016-04-07", "2016-12-09"),
        "2017-10..2018-07": ("2017-10-19", "2018-07-27"), "COVID 2020-03..2021-06": ("2020-03-16", "2021-06-30")}
START = pd.Timestamp("2011-07-01")  # DOHMH history is thin before this


def period(d: pd.Timestamp) -> str:
    for k, (a, b) in GAPS.items():
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return k
    return "other"


def era(d: pd.Timestamp) -> str:
    y = d.year
    return "2011-14" if y <= 2014 else "2015-19" if y <= 2019 else "2020-21" if y <= 2021 else "2022-26"


def stats_close(x: pd.DataFrame) -> dict:
    c = x[x["U"].notna()]
    if not len(c):
        return {"n": int(len(x))}
    w = (c["U"] - c["L"]).dt.days
    rel = ((c["d"] - c["L"]).dt.days / w.replace(0, np.nan))
    mid = c["L"] + (c["U"] - c["L"]) / 2
    e = lambda est: (est - c["d"]).dt.days
    return {
        "n_matched": int(len(x)), "n_dohmh_closed": int(len(c)),
        "share_dohmh_still_open": round(1 - len(c) / len(x), 3),
        "inside_window": round(float(((c["d"] >= c["L"]) & (c["d"] <= c["U"])).mean()), 3),
        "inside_window_plus60d": round(float(((c["d"] >= c["L"]) & (c["d"] <= c["U"] + pd.Timedelta(days=60))).mean()), 3),
        "inside_window_pm60d": round(float(((c["d"] >= c["L"] - pd.Timedelta(days=60)) & (c["d"] <= c["U"] + pd.Timedelta(days=60))).mean()), 3),
        "post_before_L": round(float((c["d"] < c["L"]).mean()), 3),
        "post_before_L_by_1y+": round(float((c["d"] < c["L"] - pd.Timedelta(days=365)).mean()), 3),
        "post_after_U": round(float((c["d"] > c["U"]).mean()), 3),
        "median_window_days": float(w.median()),
        "median_rel_position": round(float(rel.median()), 2),
        "median_err_L": float(e(c["L"]).median()), "median_abs_err_L": float(e(c["L"]).abs().median()),
        "median_err_mid": float(e(mid).median()), "median_abs_err_mid": float(e(mid).abs().median()),
        "median_err_U": float(e(c["U"]).median()), "median_abs_err_U": float(e(c["U"]).abs().median()),
    }


def stats_open(x: pd.DataFrame) -> dict:
    if not len(x):
        return {"n": 0}
    e = (x["F"] - x["d"]).dt.days
    e2 = (x[["F", "first_seen"]].min(axis=1) - x["d"]).dt.days  # first listed or inspected
    return {"n": int(len(x)), "median_err_F": float(e.median()),
            "median_err_first_listed": float(e2.median()), "median_abs_err_first_listed": float(e2.abs().median()),
            "within_90d_first_listed": round(float((e2.abs() <= 90).mean()), 3),
            "p25": float(e.quantile(.25)), "p75": float(e.quantile(.75)),
            "median_abs_err": float(e.abs().median()),
            "within_30d": round(float((e.abs() <= 30).mean()), 3),
            "within_90d": round(float((e.abs() <= 90).mean()), 3),
            "F_before_post_by_90d+": round(float((e < -90).mean()), 3),
            "F_after_post_by_180d+": round(float((e > 180).mean()), 3)}


def first_post(ev: pd.DataFrame, kinds: tuple[str, ...]) -> pd.DataFrame:
    x = ev[ev["event"].isin(kinds) & ev["biz"].notna() & ~ev["roundup"]
           & ~ev["street_conflict"].fillna(False).astype(bool)].copy()
    x["d"] = x["date"]
    x = x.sort_values("d")
    agg = x.groupby("biz").agg(d=("d", "first"), source=("source", "first"),
                               sources=("source", lambda s: sorted(set(s))), n_posts=("d", "size"),
                               title=("title", "first"), url=("url", "first"),
                               matched_name=("matched_name", "first"), via_label=("via_label", "first"))
    keep = ["dba", "camis_list", "n_camis", "F", "first_seen", "L", "U", "last_snap", "zip", "boro"]
    return agg.join(x.drop_duplicates("biz").set_index("biz")[keep]).reset_index()


def run() -> dict:
    ev = pd.read_parquet(OUT / "events.parquet")
    ev["roundup"] = ev["roundup"].fillna(False).astype(bool)
    latest = ev["last_snap"].max()
    S: dict = {"posts_by_source_event": ev.groupby(["source", "event"]).size().unstack(fill_value=0).to_dict("index")}

    # ---- match rates
    mr = {}
    for (s, e), g in ev[~ev["roundup"]].groupby(["source", "event"]):
        if e in ("close", "open", "reopen", "relocate"):
            mr[f"{s}/{e}"] = {"n": int(len(g)), "dohmh": round(float(g["biz"].notna().mean()), 3),
                              "sla_only": round(float((g["biz"].isna() & g["sla_name"].notna()).mean()), 3),
                              "ambiguous_only": round(float((g["biz"].isna() & (g["n_ambiguous"] > 0)).mean()), 3)}
    S["match_rate"] = mr

    # ---- closures
    cl = first_post(ev, ("close",))
    cl = cl[(cl["d"] >= START) & (cl["d"] <= latest)]
    cl["period"], cl["era"] = cl["d"].map(period), cl["d"].map(era)
    S["closures_overall"] = stats_close(cl)
    S["closures_by_period"] = {k: stats_close(g) for k, g in cl.groupby("period")}
    S["closures_by_era"] = {k: stats_close(g) for k, g in cl.groupby("era")}
    S["closures_by_source"] = {k: stats_close(g) for k, g in cl.groupby("source")}
    S["closures_label_vs_title"] = {str(k): stats_close(g) for k, g in cl.groupby(cl["via_label"].fillna(False))}

    # ---- false closures: DOHMH-closed businesses with a later reopen / relocate post
    rr = ev[ev["event"].isin(("reopen", "relocate")) & ev["biz"].notna()][["biz", "date", "event"]]
    closed_biz = cl[cl["U"].notna()][["biz", "L", "U", "d"]]
    j = closed_biz.merge(rr, on="biz", how="left")
    j = j[j["date"].isna() | (j["date"] > j["L"])]
    fc = j.groupby("biz")["event"].agg(lambda s: set(s.dropna()))
    S["false_closure"] = {
        "n_dohmh_closed_with_close_post": int(len(closed_biz)),
        "share_later_reopen": round(float(fc.map(lambda s: "reopen" in s).mean()), 3),
        "share_later_relocate": round(float(fc.map(lambda s: "relocate" in s).mean()), 3),
        "share_any": round(float(fc.map(bool).mean()), 3)}
    # all DOHMH-closed businesses matched by a reopen/relocate post after L
    allc = ev[ev["biz"].notna() & ev["U"].notna()]
    rr2 = allc[allc["event"].isin(("reopen", "relocate")) & (allc["date"] > allc["L"])]
    S["false_closure"]["dohmh_closed_biz_any_post"] = int(allc["biz"].nunique())
    S["false_closure"]["dohmh_closed_biz_reopen_or_relocate_after_L"] = int(rr2["biz"].nunique())
    # close posts whose DOHMH business is still listed and inspected > 180 d after the post
    alive = cl[cl["U"].isna()]
    S["false_closure"]["close_post_dohmh_alive"] = int(len(alive))
    S["false_closure"]["close_post_dohmh_alive_inspected_180d_after"] = int(
        (alive["L"] > alive["d"] + pd.Timedelta(days=180)).sum())

    # ---- missed: close posts with no DOHMH match
    cp = ev[(ev["event"] == "close") & ~ev["roundup"] & (ev["date"] >= START) & ev["food_post"]]
    S["missed"] = {k: {"n": int(len(g)), "no_dohmh": round(float(g["biz"].isna().mean()), 3),
                       "no_dohmh_but_sla": round(float((g["biz"].isna() & g["sla_name"].notna()).mean()), 3),
                       "no_dohmh_no_name_found": round(float((g["biz"].isna() & (g["n_names"] == 0) & g["sla_name"].isna()).mean()), 3),
                       "no_dohmh_not_even_loose": round(float((g["biz"].isna() & g["loose_dohmh_name"].isna() & g["sla_name"].isna()).mean()), 3)}
                   for k, g in cp.groupby("source")}

    # ---- openings
    op = first_post(ev, ("open",))
    op = op[(op["d"] >= pd.Timestamp("2012-01-01")) & (op["d"] <= latest)]
    op["period"], op["era"] = op["d"].map(period), op["d"].map(era)
    S["openings_overall"] = stats_open(op)
    S["openings_by_period"] = {k: stats_open(g) for k, g in op.groupby("period")}
    S["openings_by_era"] = {k: stats_open(g) for k, g in op.groupby("era")}
    S["openings_by_source"] = {k: stats_open(g) for k, g in op.groupby("source")}

    for df, name in ((cl, "eval_closures"), (op, "eval_openings")):
        df.to_parquet(OUT / f"{name}.parquet", index=False)
    (OUT / "summary.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v for k, v in S.items() if k != "posts_by_source_event"}, indent=1, default=str))
    return S


if __name__ == "__main__":
    run()
