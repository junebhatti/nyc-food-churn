"""NYT restaurant reviews with stars (metadata only: name, stars, date, critic, neighborhood).

Source: github.com/maks-p/nyt_restaurant_reviews_NLP reviews.csv (no license stated;
scraped from the NYT restaurant-guide listings ~2019). We keep only factual metadata,
no review text. Coverage roughly 2004-2019 (Bruni, Sifton, Wells).
For newer reviews use the NYT Article Search API (free key; see data/notes/ratings.md).
"""
from __future__ import annotations

import gzip
import io
import json

import pandas as pd

import ratings_common as rc

URL = "https://raw.githubusercontent.com/maks-p/nyt_restaurant_reviews_NLP/master/reviews.csv"
NTA = rc.RAW / "gov" / "geo_nta2020.geojson.gz"
EXTRA_HOODS = {"Williamsburg": "Brooklyn", "Greenpoint": "Brooklyn", "Bushwick": "Brooklyn",
               "Long Island City": "Queens", "Flushing": "Queens", "Astoria": "Queens",
               "Jackson Heights": "Queens", "Elmhurst": "Queens", "Sunnyside": "Queens"}
MANHATTAN_WORDS = ["Village", "Midtown", "SoHo", "Soho", "TriBeCa", "Tribeca", "NoHo", "Nolita",
                   "Chelsea", "Flatiron", "Gramercy", "Murray Hill", "Harlem", "Upper", "Lower",
                   "Financial District", "Chinatown", "Little Italy", "Theater District", "Hell's Kitchen",
                   "Clinton", "Kips Bay", "Union Square", "Battery Park", "Columbus Circle",
                   "Meatpacking", "Times Square", "Hudson Yards", "NoMad", "Nomad", "Morningside",
                   "Washington Heights", "Inwood", "East Side", "West Side"]


def borough_lookup() -> dict[str, str]:
    g = json.load(gzip.open(NTA))
    out = {}
    for f in g["features"]:
        p = f["properties"]
        for part in p["ntaname"].replace("(", "-").replace(")", "").split("-"):
            part = part.strip()
            if len(part) > 3:
                out.setdefault(part, p["boroname"])
    out.update(EXTRA_HOODS)
    return out


def to_borough(hood: str, lut: dict[str, str]) -> str | None:
    if not isinstance(hood, str):
        return None
    for b in ["Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"]:
        if b in hood:
            return b
    if hood in lut:
        return lut[hood]
    if any(w in hood for w in MANHATTAN_WORDS):
        return "Manhattan"
    hits = {b for k, b in lut.items() if k in hood or hood in k}
    return hits.pop() if len(hits) == 1 else None


def run() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(rc.get(URL).text), index_col=0)
    df = df[["name", "rating", "review_date", "reviewer", "neighborhood", "cuisine", "review_link_1"]]
    df = df.rename(columns={"review_link_1": "review_url", "rating": "rating_raw"})
    # the source encodes NYT's sub-one-star grades as fractions (0.25-0.75 = poor/fair/satisfactory)
    df["stars"] = pd.to_numeric(df.rating_raw.str.extract(r"([\d.]+)", expand=False), errors="coerce")
    raw_date = df.review_date
    df["review_date"] = pd.to_datetime(raw_date, errors="coerce", format="mixed")
    # fall back to the /YYYY/MM/DD/ in the article URL
    url_date = pd.to_datetime(df.review_url.str.extract(r"/(\d{4}/\d{2}/\d{2})/", expand=False),
                              format="%Y/%m/%d", errors="coerce")
    df["review_date"] = df.review_date.fillna(url_date)
    if df.review_date.isna().any():
        print(f"NYT: {df.review_date.isna().sum()} reviews without a parseable date, e.g. "
              f"{raw_date[df.review_date.isna()].head(3).tolist()}")
    df["year"] = df.review_date.dt.year
    lut = borough_lookup()
    df["borough"] = df.neighborhood.map(lambda h: to_borough(h, lut))
    df = df.reset_index(drop=True)
    df["rid"] = df.index
    c = rc.connect()
    with_b = rc.match_name(c, df[df.borough.notna()], "rid", boro_col="borough")
    no_b = rc.match_name(c, df[df.borough.isna()], "rid")
    df = df.merge(pd.concat([with_b, no_b]), on="rid", how="left").drop(columns="rid")
    df["list"] = "nyt_review"
    df["source"] = "github:maks-p/nyt_restaurant_reviews_NLP"
    rc.write(df, "nyt_reviews")
    print(f"NYT: {len(df)} reviews {df.year.min():.0f}-{df.year.max():.0f}; stars "
          f"{df.stars.value_counts().sort_index().to_dict()}; borough known {df.borough.notna().mean():.0%}; "
          f"CAMIS match {df.camis.notna().mean():.0%} (reviews since 2011: "
          f"{df[df.year >= 2011].camis.notna().mean():.0%})")
    return df


if __name__ == "__main__":
    run()
