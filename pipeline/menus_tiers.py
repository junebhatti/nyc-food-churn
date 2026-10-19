"""Price tier per CAMIS: cheap / mid / upscale / fine -> data/raw/menus/camis_price_tier.parquet

Rule (first that applies; tier_source says which):
  1. michelin    any Michelin star, or NYT 3-4 stars                          -> fine
  2. menu        MenuPages median main course (>=5 mains), in 2015 dollars:
                 < $12 cheap, $12-18 mid, $18-30 upscale, >= $30 fine
                 (cut points follow MenuPages' own avg-entree key: $-$$ <12, $$$ 12-18,
                 $$$$ 18-25, $$$$$ >25); a tasting/prix-fixe item >= $75 also -> fine
  3. guide       Zagat cost/person (2015 $): <=25 cheap, 26-40 mid, 41-65 upscale, 66+ fine;
                 else NY Mag $-$$$$ (1-4 -> cheap..fine)
  3b. menu_level MenuPages $-rating alone: 1-2 cheap, 3 mid, 4-5 upscale
  4. stated      Google Local / Michelin Guide $-level: $ cheap, $$ mid, $$$ upscale, $$$$ fine
  5. proxy       modal tier of CAMIS with a real signal (2-4) in the same proxy cell
                 (fast_food x chain x liquor x cuisine group); cells with < 20 labels fall back
                 to (fast_food x liquor). Accuracy of this fallback is printed (holdout).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from menus_common import OUT, ROOT

RAT = ROOT / "data" / "raw" / "ratings"
TIERS = ["cheap", "mid", "upscale", "fine"]
# CPI-U "food away from home" (US city avg), annual, rebased 2015 = 1 (approximate)
FAFH = {2009: .885, 2010: .899, 2011: .915, 2012: .940, 2013: .961, 2014: .983, 2015: 1.0,
        2016: 1.026, 2017: 1.049, 2018: 1.080, 2019: 1.112, 2020: 1.146, 2021: 1.199,
        2022: 1.293, 2023: 1.383, 2024: 1.440, 2025: 1.495, 2026: 1.540}
CUISINE_GROUP = {
    "pizza": "Pizza|Pizza/Italian", "chinese": "Chinese", "latin": "Latin|Spanish|Mexican|Tex-Mex|Peruvian|Caribbean|Brazilian",
    "cafe_bakery": "Coffee|Café|Bakery|Donuts|Bagels|Juice|Frozen|Ice Cream|Pancakes",
    "fastfood": "Hamburgers|Chicken|Hotdogs|Sandwiches|Salads|Delicatessen|Soups",
    "japanese": "Japanese|Sushi", "italian": "^Italian", "french": "French|Continental|Haute",
    "steak_seafood": "Steak|Seafood", "american": "American|Californian|Barbecue|Soul",
    "asian_other": "Korean|Thai|Asian|Vietnamese|Indian|Pakistani|Bangladeshi|Filipino|Southeast",
    "med_mideast": "Mediterranean|Middle Eastern|Greek|Turkish|Lebanese|Moroccan|Tapas",
}


def cuisine_group(s: pd.Series) -> pd.Series:
    out = pd.Series("other", index=s.index)
    for g, pat in reversed(list(CUISINE_GROUP.items())):
        out = out.where(~s.fillna("").str.contains(pat, regex=True), g)
    return out


def tier_from_price(p: pd.Series) -> pd.Series:
    return pd.cut(p, [-np.inf, 12, 18, 30, np.inf], right=False, labels=TIERS).astype("string")


def menu_signal() -> pd.DataFrame:
    mp = pd.read_parquet(OUT / "menupages.parquet")
    mp = mp[mp.camis.notna()].copy()
    yr = mp.snapshot_date.dt.year
    mp["main_2015"] = mp.median_main_price / yr.map(FAFH)
    it = pd.read_parquet(OUT / "menupages_items.parquet")
    tasting = it[it.section.str.contains("tasting|prix|chef.s menu|omakase", case=False, na=False)
                 & (it.price >= 75)].slug.unique()
    mp["tasting75"] = mp.slug.isin(tasting)
    # one record per CAMIS: most priced items
    mp = mp.sort_values("n_items_priced").groupby("camis").tail(1)
    t = tier_from_price(mp.main_2015.where(mp.n_main_items >= 5))
    t = t.where(~mp.tasting75, "fine")
    lvl = mp.price_level_n.map({1: "cheap", 2: "cheap", 3: "mid", 4: "upscale", 5: "upscale"})
    return pd.DataFrame({"camis": mp.camis, "menu_tier": t, "menu_level_tier": lvl.astype("string"),
                         "menu_main_2015": mp.main_2015, "menu_n_items": mp.n_items_priced,
                         "menu_snapshot": mp.snapshot_date, "menu_price_level": mp.price_level})


def stated_signal() -> pd.DataFrame:
    rows = []
    g = pd.read_parquet(RAT / "google_local_nyc.parquet", columns=["camis", "price"])
    g["n"] = g.price.str.count(r"[$₩]")
    rows.append(g[["camis", "n"]].assign(src="google"))
    s = pd.read_parquet(RAT / "michelin_guide_nyc_snapshots.parquet", columns=["camis", "price"])
    s["n"] = s.price.str.count(r"\$")
    rows.append(s[["camis", "n"]].assign(src="michelin_guide"))
    st = pd.concat(rows).dropna(subset=["camis"])
    st = st[st.n.between(1, 4)].groupby("camis").n.median().round().astype(int)
    return pd.DataFrame({"camis": st.index, "stated_tier": st.map(dict(enumerate(TIERS, 1))).values})


def guide_signal() -> pd.DataFrame:
    """Zagat cost per person (2015 $; Zagat's key: <=25 I, 26-40 M, 41-65 E, 66+ VE) and
    NY Mag $-$$$$. Empty until menus_guides.py build has run."""
    p = OUT / "guides.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["camis", "guide_tier"])
    g = pd.read_parquet(p)
    g = g[g.camis.notna()].copy()
    cost = g.cost / g.snapshot_date.dt.year.map(FAFH)
    zt = pd.cut(cost, [-np.inf, 25.5, 40.5, 65.5, np.inf], labels=[1, 2, 3, 4]).astype(float)
    g["n"] = zt.fillna(g.price_level_n.clip(upper=4))
    g = g.dropna(subset=["n"]).groupby("camis").n.median().round().astype(int)
    return pd.DataFrame({"camis": g.index, "guide_tier": g.map(dict(enumerate(TIERS, 1))).values})


def fine_signal() -> set:
    m = pd.read_parquet(RAT / "michelin_nyc.parquet", columns=["camis", "stars"])
    s = pd.read_parquet(RAT / "michelin_guide_nyc_snapshots.parquet", columns=["camis", "award_level"])
    n = pd.read_parquet(RAT / "nyt_reviews.parquet", columns=["camis", "stars"])
    return (set(m[m.stars >= 1].camis.dropna()) | set(s[s.award_level.str.contains("star", na=False)].camis.dropna())
            | set(n[n.stars >= 3].camis.dropna()))


def proxy_tier(df: pd.DataFrame, label: pd.Series, seed: int = 7) -> tuple[pd.Series, float]:
    cell = (df.fast_food.astype(str) + "|" + df.chain.astype(str) + "|" + df.liquor + "|" + df.cgroup)
    coarse = df.fast_food.astype(str) + "|" + df.liquor
    lab = label.dropna()
    rng = np.random.default_rng(seed)
    test = lab.index[rng.random(len(lab)) < 0.2]

    def fit(train_idx):
        tr = pd.DataFrame({"cell": cell[train_idx], "coarse": coarse[train_idx], "t": label[train_idx]})
        fine_mode = tr.groupby("cell").t.agg(lambda s: s.mode().iat[0] if len(s) >= 20 else None)
        coarse_mode = tr.groupby("coarse").t.agg(lambda s: s.mode().iat[0])
        out = cell.map(fine_mode)
        out = out.where(out.notna(), coarse.map(coarse_mode))
        return out.fillna(tr.t.mode().iat[0])

    pred_test = fit(lab.index.difference(test))
    acc = float((pred_test[test] == label[test]).mean()) if len(test) else float("nan")
    return fit(lab.index), acc


def build() -> pd.DataFrame:
    px = pd.read_parquet(OUT / "camis_proxies.parquet")
    px["cgroup"] = cuisine_group(px.cuisine)
    df = px.merge(menu_signal(), on="camis", how="left").merge(stated_signal(), on="camis", how="left")
    df = df.merge(guide_signal(), on="camis", how="left")
    df.index = range(len(df))
    fine = df.camis.isin(fine_signal())
    # proxy cells are calibrated on every CAMIS with a real price signal (menu first)
    real = df.menu_tier.fillna(df.guide_tier).fillna(df.menu_level_tier).fillna(df.stated_tier)
    proxy, acc = proxy_tier(df, real)
    df["tier"], df["tier_source"] = proxy, "proxy"
    for mask, val, src in [(df.stated_tier.notna(), df.stated_tier, "stated"),
                           (df.menu_level_tier.notna(), df.menu_level_tier, "menu_level"),
                           (df.guide_tier.notna(), df.guide_tier, "guide"),
                           (df.menu_tier.notna(), df.menu_tier, "menu"),
                           (fine, pd.Series("fine", index=df.index), "michelin")]:
        df.loc[mask, "tier"] = val[mask]
        df.loc[mask, "tier_source"] = src
    out = df[["camis", "dba", "cuisine", "cgroup", "open_year", "liquor", "chain", "fast_food",
              "menu_tier", "menu_level_tier", "menu_main_2015", "menu_n_items", "menu_snapshot",
              "menu_price_level", "guide_tier", "stated_tier", "tier", "tier_source"]]
    out.to_parquet(OUT / "camis_price_tier.parquet", index=False)
    print(f"proxy-cell holdout accuracy vs real tiers (20% holdout): {acc:.1%}")
    print(out.tier_source.value_counts(normalize=True).round(3).to_string())
    print(pd.crosstab(out.tier_source, out.tier).to_string())
    yr = out.open_year.clip(upper=2026).astype("Int64").astype(str).replace({"2010": "<=2011", "2011": "<=2011"})
    tab = pd.crosstab(yr, out.tier_source, normalize="index").round(3)
    print(tab.to_string())
    tab.to_csv(OUT / "tier_source_by_open_year.csv")
    return out


if __name__ == "__main__":
    build()
