"""Official-statistics benchmark for NYC restaurant/bar counts and churn.

Usage: .venv/bin/python pipeline/fetch_benchmarks.py [fetch|compare|all]   (default: all)

fetch   -> Census CBP county, ZBP ZIP detail, BDS, Nonemployer (bench_census.py) and
           BLS QCEW quarterly + BED openings/closings (bench_bls.py) into data/raw/benchmarks/
compare -> coverage ratios + closure-rate comparison against the DOHMH union (bench_compare.py)

Set BENCH_DL to a scratch dir for the temporary source zips (default data/raw/benchmarks/_dl);
each zip is deleted after filtering. See data/notes/benchmarks.md.
"""
import sys

import bench_bls
import bench_census
import bench_compare
from bench_common import OUT, log


def fetch():
    OUT.mkdir(parents=True, exist_ok=True)
    bench_census.cbp_county()
    bench_census.zbp_detail()
    bench_census.bds()
    bench_census.nonemployer()
    bench_bls.bed()
    bench_bls.qcew()
    for u, why in bench_census.MISSING:
        log(f"MISSING {u}: {why}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("fetch", "all"):
        fetch()
    if step in ("compare", "all"):
        bench_compare.main()
