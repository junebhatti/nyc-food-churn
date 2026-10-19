"""UCSD McAuley lab "Google Local" (2018 release; He, Kang & McAuley RecSys'17,
Pasricha & McAuley RecSys'18). Research use; cite those papers.

Source: https://mcauleylab.ucsd.edu/public_datasets/data/googlelocal/
  places.clean.json.gz   291 MB, ~3.1M places worldwide (name, address, gps, closed flag)
  reviews.clean.json.gz  1.49 GB, ~11.4M reviews (place id, unix time, place categories)
Both are streamed and filtered on the fly (nothing global kept). Lines are Python
dict literals, not JSON.

Places carry no category, so food/drink is decided from the categories attached
to the place's reviews.
Output: research_poi/gl2018_venues.parquet, gl2018_yearly.parquet
"""
from __future__ import annotations

import ast
import gzip
import io
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pandas as pd

import rpoi_common as rc

BASE = "https://mcauleylab.ucsd.edu/public_datasets/data/googlelocal/"
GPS = re.compile(r"'gps': \[(-?[\d.]+), (-?[\d.]+)\]")
NYC_ZIP = re.compile(r"\bNY (1\d{4})\b")
PID = re.compile(r"'gPlusPlaceId': u?'(\d+)'")
TIME = re.compile(r"'unixReviewTime': (\d+)")
CATS = re.compile(r"'categories': (\[.*?\]|None)")


def nyc_zip(z: str) -> bool:
    return ("10001" <= z <= "10282" or "10301" <= z <= "10314" or "10451" <= z <= "10475"
            or "11004" <= z <= "11005" or "11101" <= z <= "11697")


def stream_lines(url: str):
    with rc.get(BASE + url, stream=True) as r:
        r.raw.decode_content = False
        with gzip.GzipFile(fileobj=r.raw) as gz:
            for line in io.TextIOWrapper(gz, encoding="utf-8", errors="replace"):
                yield line


def load_places() -> pd.DataFrame:
    rows, n = [], 0
    for line in stream_lines("places.clean.json.gz"):
        n += 1
        m = GPS.search(line)
        if not m or not rc.in_bbox(float(m.group(1)), float(m.group(2))):
            continue
        try:
            p = ast.literal_eval(line)
        except (ValueError, SyntaxError) as e:
            print(f"  unparsable place line {n}: {e!r}: {line[:120]}")
            continue
        addr = p.get("address") or []
        zm = NYC_ZIP.search(" ".join(addr))
        if not zm or not nyc_zip(zm.group(1)):
            continue
        rows.append({"venue_id": p["gPlusPlaceId"], "name": p.get("name"),
                     "lat": p["gps"][0], "lon": p["gps"][1], "address": "; ".join(addr),
                     "zipcode": zm.group(1), "price": p.get("price"),
                     "closed_2018": bool(p.get("closed")), "phone": p.get("phone")})
    print(f"  places scanned {n:,}; NYC by ZIP {len(rows):,}")
    if not rows:
        raise RuntimeError("no NYC places parsed from Google Local 2018")
    return pd.DataFrame(rows).drop_duplicates("venue_id")


def load_reviews(ids: set[str]):
    daily = Counter()
    cats: dict[str, Counter] = defaultdict(Counter)
    n = kept = bad = 0
    for line in stream_lines("reviews.clean.json.gz"):
        n += 1
        m = PID.search(line)
        if not m or m.group(1) not in ids:
            continue
        t = TIME.search(line)
        if not t:
            bad += 1
            continue
        pid = m.group(1)
        d = datetime.fromtimestamp(int(t.group(1)), tz=timezone.utc).date()
        daily[(pid, d)] += 1
        kept += 1
        cm = CATS.search(line)
        if cm and cm.group(1) != "None":
            try:
                for cat in ast.literal_eval(cm.group(1)):
                    cats[pid][cat] += 1
            except (ValueError, SyntaxError):
                bad += 1
    print(f"  reviews scanned {n:,}; NYC kept {kept:,}; lines missing time/categories {bad:,}")
    acts = pd.DataFrame([(k[0], k[1], v) for k, v in daily.items()], columns=["venue_id", "d", "n"])
    cat = pd.DataFrame([(pid, "; ".join(c for c, _ in cs.most_common(5))) for pid, cs in cats.items()],
                       columns=["venue_id", "category"])
    return acts, cat


def run() -> None:
    places = load_places()
    acts, cat = load_reviews(set(places.venue_id))
    v = places.merge(cat, on="venue_id", how="left")
    cats = v.category.fillna("")
    top = cats.str.split(";").str[0]
    food = cats.str.contains(rc.FOOD) & ~top.str.contains(rc.NOT_FOOD)
    print(f"  NYC places with reviews {v.venue_id.isin(acts.venue_id).sum():,}; food/drink {food.sum():,}")
    c = rc.connect()
    rc.df_to(c, v[food], "v")
    rc.df_to(c, acts, "a")
    c.execute("alter table a alter d type date")
    # ~500 places carry a placeholder 1990-12-31 review time; Google reviews start ~2002.
    junk = c.execute("select count(*) from a where d < '2002-01-01'").fetchone()[0]
    print(f"  dropped {junk:,} venue-days dated before 2002 (placeholder timestamps)")
    c.execute("delete from a where d < '2002-01-01'")
    rc.write_venues(c, "gl2018", "v", "a")


if __name__ == "__main__":
    run()
