"""Geography: 2020 NTAs, 2020 census tracts, boroughs, BIDs (GeoJSON, gzipped) and a slim PLUTO
(bbl -> address, lat/lon, land use, building class, ct2020, nta2020)."""
from __future__ import annotations

import gzip
import json

import pandas as pd

from gov_common import OUT, get, register_file, save, socrata

NYC = "data.cityofnewyork.us"
BOUNDARIES = {
    "nta2020": "9nt8-h7nd", "census_tracts2020": "63ge-mke6",
    "boroughs": "gthc-hcne", "bids": "7jdm-inj8",
}
PLUTO_COLS = ("bbl,borough,borocode,block,lot,address,zipcode,latitude,longitude,landuse,"
              "bldgclass,bct2020,cd,council,lotarea,bldgarea,comarea,retailarea,officearea,"
              "resarea,unitsres,unitstotal,numfloors,yearbuilt,version")


def boundaries():
    for name, dsid in BOUNDARIES.items():
        r = get(f"https://{NYC}/api/geospatial/{dsid}", params={"method": "export", "format": "GeoJSON"})
        gj = r.json()
        n = len(gj.get("features", []))
        if n == 0:
            raise RuntimeError(f"{name} ({dsid}): empty GeoJSON")
        path = OUT / f"geo_{name}.geojson.gz"
        path.write_bytes(gzip.compress(json.dumps(gj).encode()))
        register_file(f"geo_{name}", path, source=NYC, dataset_id=dsid, rows=n,
                      fields=list(gj["features"][0]["properties"]), note="GeoJSON (EPSG:4326), gzip")
        print(f"saved {path.name}: {n} features, {path.stat().st_size/1e6:.1f} MB")


def pluto(eq: pd.DataFrame):
    df = socrata(NYC, "64uk-42ks", select=PLUTO_COLS)
    df["bbl"] = pd.to_numeric(df["bbl"], errors="coerce").astype("Int64").astype("string")
    for c in ("latitude", "longitude", "lotarea", "bldgarea", "comarea", "retailarea",
              "officearea", "resarea", "unitsres", "unitstotal", "numfloors", "yearbuilt"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.rename(columns={"latitude": "lat", "longitude": "lon"})
    df = df.merge(eq[["boroct2020", "ntacode", "ntaname", "cdtacode"]]
                  .rename(columns={"boroct2020": "bct2020", "ntacode": "nta2020"}),
                  on="bct2020", how="left")
    df["ct2020"] = df["bct2020"].str[1:]
    missing = df["nta2020"].isna().mean()
    print(f"  PLUTO lots without nta2020: {missing:.2%}")
    save(df, "pluto_slim", source=NYC, dataset_id="64uk-42ks",
         note=f"PLUTO {df['version'].dropna().iloc[0]} slim; nta2020 via bct2020 -> hm78-6dwm.")


def run():
    print("== Geography")
    boundaries()
    eq = socrata(NYC, "hm78-6dwm")
    save(eq, "ct2020_nta2020_equiv", source=NYC, dataset_id="hm78-6dwm",
         note="2020 census tract -> NTA/CDTA equivalency")
    pluto(eq)


if __name__ == "__main__":
    run()
