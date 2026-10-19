"""Ground truth for opening / closing dates: blog + Eater + Grub Street post metadata,
matched to DOHMH businesses, and an accuracy check of the inferred dates.

    .venv/bin/python pipeline/fetch_groundtruth.py [blogs wayback match eval manifest]

Steps (default: all, in this order):
  blogs    gt_blogs.py    Blogger / WordPress feeds -> posts_blogs.parquet (cached pages)
  wayback  gt_wayback.py  Eater NY + Grub Street URL slugs from Wayback CDX -> posts_wayback.parquet
  match    gt_match.py    events + DOHMH / SLA match -> events.parquet
  eval     gt_eval.py     eval_closures / eval_openings.parquet, summary.json
  manifest               manifest.json (rows, date range, columns per file)
See data/notes/groundtruth.md.
"""
from __future__ import annotations

import json
import sys
from datetime import date

import pandas as pd

from gt_common import OUT


def manifest() -> None:
    files = {}
    for p in sorted(OUT.glob("*.parquet")):
        df = pd.read_parquet(p)
        dcol = "date" if "date" in df else "d" if "d" in df else None
        files[p.name] = {"rows": len(df), "bytes": p.stat().st_size, "columns": list(df.columns),
                         "date_min": str(df[dcol].min().date()) if dcol and len(df) else None,
                         "date_max": str(df[dcol].max().date()) if dcol and len(df) else None,
                         "by_source": df["source"].value_counts().to_dict() if "source" in df else None}
    m = {"built": str(date.today()), "files": files,
         "note": "Metadata only (title or URL slug, date, URL, labels, extracted names); no article text."}
    (OUT / "manifest.json").write_text(json.dumps(m, indent=1, default=str))
    print(f"wrote manifest.json ({len(files)} files)")


def main(steps: list[str]) -> None:
    steps = steps or ["blogs", "wayback", "match", "eval", "manifest"]
    for s in steps:
        print(f"== {s}", flush=True)
        if s == "blogs":
            import gt_blogs; gt_blogs.run()
        elif s == "wayback":
            import gt_wayback; gt_wayback.run()
        elif s == "match":
            import gt_match; gt_match.run()
        elif s == "eval":
            import gt_eval; gt_eval.run()
        elif s == "manifest":
            manifest()
        else:
            raise SystemExit(f"unknown step {s!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
