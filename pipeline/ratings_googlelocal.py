"""UCSD McAuley lab "Google Local Data (2021)", New York state -> NYC food & drink.

Source: https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/
  (research use; cite Li et al. UCTopic ACL'22 and Yan et al. SIGIR'23).
Inputs (downloaded to data/raw/ratings/_dl/ and deleted afterwards unless --keep):
  meta-New_York.json.gz    61 MB, 272k businesses (name, address, lat/lon, category,
                           avg_rating, num_of_reviews, price, hours, state)
  rating-New_York.csv.gz  638 MB, 33.5M (business, user, rating, timestamp ms)
Outputs:
  google_local_nyc.parquet        one row per NYC food/drink business + review stats
                                  (first/last review date = proof-of-life window) + CAMIS
  google_local_nyc_yearly.parquet business x year: n_reviews, mean_rating
"""
from __future__ import annotations

import sys

import ratings_common as rc

BASE = "https://mcauleylab.ucsd.edu/public_datasets/gdrive/googlelocal/"
FILES = ["meta-New_York.json.gz", "rating-New_York.csv.gz"]
DL = rc.OUT / "_dl"

FOOD = (r"(?i)restaurant|\bcaf[eé]|coffee|\bbar\b|\bpub\b|bakery|pizz|deli\b|diner|bistro|"
        r"brewery|brewpub|tavern|lounge|tea house|bubble tea|dessert|ice cream|frozen yogurt|"
        r"juice|bagel|donut|doughnut|taco|taqueria|sushi|ramen|noodle|steak|food court|"
        r"gastropub|wine bar|cocktail|beer|izakaya|dumpling|sandwich|burger|chicken wings|"
        r"barbecue|bbq|meal takeaway|meal delivery|caterer|food truck|creperie|patisserie|"
        r"cupcake|chocolate|gelato|bar & grill|night club|hookah|karaoke bar")


def download() -> None:
    DL.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        p = DL / f
        if p.exists() and p.stat().st_size > 0:
            continue
        print("downloading", f)
        with rc.get(BASE + f, stream=True) as r, open(p, "wb") as out:
            for chunk in r.iter_content(1 << 20):
                out.write(chunk)


def run(keep: bool = False) -> None:
    download()
    c = rc.connect()
    c.execute(f"""
    create table meta as
    select gmap_id, name, address, latitude lat, longitude lon,
           array_to_string(category, '; ') category, avg_rating, num_of_reviews, price,
           state, description,
           regexp_extract(address, 'NY (1\\d{{4}})', 1) zipcode,
           to_json(hours) "hours", to_json(MISC) misc, url
    from read_json('{DL / FILES[0]}', format='newline_delimited', maximum_object_size=50000000,
                   columns={{name:'VARCHAR', address:'VARCHAR', gmap_id:'VARCHAR', description:'VARCHAR',
                            latitude:'DOUBLE', longitude:'DOUBLE', category:'VARCHAR[]',
                            avg_rating:'DOUBLE', num_of_reviews:'BIGINT', price:'VARCHAR',
                            hours:'VARCHAR[][]', MISC:'JSON', state:'VARCHAR',
                            relative_results:'VARCHAR[]', url:'VARCHAR'}})
    where latitude between 40.49 and 40.92 and longitude between -74.27 and -73.68
      and regexp_matches(array_to_string(category, '; '), '{FOOD}')
    qualify row_number() over (partition by gmap_id order by num_of_reviews desc nulls last) = 1
    """)
    # Keep NYC ZIPs only (bbox also catches NJ / Westchester / Nassau).
    c.execute(f"""delete from meta where zipcode = '' or not (
        zipcode between '10001' and '10282' or zipcode between '10301' and '10314'
        or zipcode between '10451' and '10475' or zipcode between '11004' and '11005'
        or zipcode between '11101' and '11697')""")
    print("meta NYC food rows:", c.execute("select count(*) from meta").fetchone()[0])
    c.execute(f"""
    create table rv as
    select business gmap_id, rating, to_timestamp(timestamp / 1000)::date d
    from read_csv('{DL / FILES[1]}', header=true,
                  columns={{business:'VARCHAR', user:'VARCHAR', rating:'INT', timestamp:'BIGINT'}})
    where business in (select gmap_id from meta)
    """)
    print("reviews kept:", c.execute("select count(*) from rv").fetchone()[0])
    c.execute("""
    create table yearly as
    select gmap_id, year(d) "year", count(*) n_reviews, round(avg(rating), 3) mean_rating
    from rv group by 1, 2 order by 1, 2
    """)
    c.execute("""
    create table stats as
    select gmap_id, count(*) n_reviews_in_file, round(avg(rating), 3) mean_rating_file,
           min(d) first_review, max(d) last_review,
           quantile_cont(epoch(d), 0.05) p05, quantile_cont(epoch(d), 0.95) p95
    from rv group by 1
    """)
    df = c.execute("""
    select m.*, s.n_reviews_in_file, s.mean_rating_file, s.first_review, s.last_review,
           to_timestamp(s.p05)::date review_p05, to_timestamp(s.p95)::date review_p95,
           m.state ilike '%permanently closed%' perm_closed_2021,
           m.state ilike '%temporarily closed%' temp_closed_2021
    from meta m left join stats s using (gmap_id)
    """).df()
    m = rc.match_geo(c, df.rename(columns={"gmap_id": "gid"}), "gid").rename(columns={"gid": "gmap_id"})
    df = df.merge(m, on="gmap_id", how="left")
    df["source"] = "ucsd_google_local_2021"
    rc.write(df, "google_local_nyc")
    rc.write(c.execute("select * from yearly").df(), "google_local_nyc_yearly")
    print(f"CAMIS match: {df.camis.notna().mean():.1%} of businesses; "
          f"{df[df.category.str.contains('(?i)restaurant')].camis.notna().mean():.1%} of 'restaurant' ones")
    if not keep:
        for f in FILES:
            (DL / f).unlink(missing_ok=True)


if __name__ == "__main__":
    run(keep="--keep" in sys.argv)
