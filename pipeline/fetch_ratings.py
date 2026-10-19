"""Ratings / critics / buzz sources -> data/raw/ratings/*.parquet. See data/notes/ratings.md.

Run: .venv/bin/python pipeline/fetch_ratings.py [michelin guide awards nyt eater google]
(no args = all; about 25 min, mostly the Wayback fetches and the 640 MB Google Local download,
which is deleted after aggregation).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ratings_awards  # noqa: E402
import ratings_eater  # noqa: E402
import ratings_googlelocal  # noqa: E402
import ratings_michelin  # noqa: E402
import ratings_nyt  # noqa: E402

STEPS = {
    "michelin": ratings_michelin.run,          # Wikipedia stars by guide year 2006-2025
    "guide": ratings_michelin.guide_snapshots,  # michelin-my-maps git history 2022-07 -> now
    "awards": ratings_awards.run,              # James Beard winners + World's 50 Best
    "nyt": ratings_nyt.run,                    # NYT stars metadata 2004-2019
    "eater": ratings_eater.run,                # Eater 38 + heatmaps via Wayback
    "google": ratings_googlelocal.run,         # UCSD Google Local 2021 NYC subset
}

if __name__ == "__main__":
    for name in sys.argv[1:] or list(STEPS):
        print(f"== {name}")
        STEPS[name]()
