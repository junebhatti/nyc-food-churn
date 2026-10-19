"""Step 5 of the merge: validate data/processed/ against independent references.

1. Integrity: unique ids, no negative lifespans, coordinates inside NYC.
2. Exit rate per year (closures / businesses open on Jan 1) vs Census BDS for NAICS 72 in the
   NYC counties (data/raw/benchmarks/closure_rates.csv). Ours should sit a little above BDS,
   since DOHMH also covers tiny non-employer places.
3. Closure dates vs dated closing posts (data/raw/groundtruth/eval_closures.parquet): share of
   posts within 60 days of our estimate, and median absolute error, against the plain window
   midpoint (L + U) / 2 as a baseline.

Writes data/processed/checks.json. Run: .venv/bin/python pipeline/build_checks.py
"""
from __future__ import annotations

import json

import pandas as pd

from build_lifespans import OUT, RAW


def integrity(b: pd.DataFrame) -> dict:
    return {
        "businesses": len(b),
        "duplicate_ids": int(b["business_id"].duplicated().sum()),
        "negative_lifespans": int((b["lifespan_days"] < 0).sum()),
        "share_with_coords": round(float(b["lat"].between(40.4, 41.0).mean()), 4),
    }


def exit_rates(b: pd.DataFrame) -> pd.DataFrame:
    d = b[b["source"] == "dohmh"]
    rows = []
    for y in range(2013, 2026):
        jan1 = pd.Timestamp(f"{y}-01-01")
        alive = d[(d["open_date"] < jan1) & (d["end_date"] >= jan1)]
        exits = alive["closed"] & (alive["close_date"] < pd.Timestamp(f"{y + 1}-01-01"))
        rows.append({"year": y, "open_jan1": len(alive), "exit_rate": round(100 * exits.mean(), 2)})
    ours = pd.DataFrame(rows)
    ref = pd.read_csv(RAW / "benchmarks" / "closure_rates.csv")
    ref = ref[ref["borough"] == "NYC"][["year", "bds72_cty_exit"]]
    return ours.merge(ref, on="year", how="left")


def closing_posts(b: pd.DataFrame) -> dict:
    gt = pd.read_parquet(RAW / "groundtruth" / "eval_closures.parquet",
                         columns=["camis_list", "d", "L", "U", "period"])
    gt = gt.dropna(subset=["U"]).reset_index(drop=True).reset_index(names="post")
    x = gt.explode("camis_list").rename(columns={"camis_list": "camis"})
    x["camis"] = x["camis"].astype(str)
    perm = b[["business_id", "camis_list", "close_date"]].explode("camis_list")
    perm = perm.rename(columns={"camis_list": "camis"})
    perm["camis"] = perm["camis"].astype(str)
    m = x.merge(perm.dropna(subset=["close_date"]), on="camis").drop_duplicates("post")
    d = pd.to_datetime(m["d"])
    ours = (d - m["close_date"]).dt.days
    mid = (d - (pd.to_datetime(m["L"]) + (pd.to_datetime(m["U"]) - pd.to_datetime(m["L"])) / 2)).dt.days
    return {
        "posts_matched": len(m),
        "ours_within_60d": round(float((ours.abs() <= 60).mean()), 3),
        "ours_median_abs_err_days": float(ours.abs().median()),
        "ours_median_signed_err_days": float(ours.median()),
        "midpoint_within_60d": round(float((mid.abs() <= 60).mean()), 3),
        "midpoint_median_abs_err_days": float(mid.abs().median()),
    }


def main() -> None:
    b = pd.read_parquet(OUT / "businesses.parquet")
    ex = exit_rates(b)
    yrs = ex["year"].between(2013, 2019)
    out = {"integrity": integrity(b), "closing_posts": closing_posts(b),
           "exit_rate_2013_19_ours": round(float(ex.loc[yrs, "exit_rate"].mean()), 2),
           "exit_rate_2013_19_bds": round(float(ex.loc[yrs, "bds72_cty_exit"].mean()), 2),
           "exit_rate_by_year": ex.to_dict("records")}
    (OUT / "checks.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "exit_rate_by_year"}, indent=1))
    print(ex.to_string(index=False))


if __name__ == "__main__":
    main()
