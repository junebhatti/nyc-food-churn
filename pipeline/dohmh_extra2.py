"""Fetch round-3 extra DOHMH copies (GitHub history, TidyTuesday) into data/raw/dohmh/extra2/.

Each copy is written as extra2/<name>.csv.gz and registered in manifest.csv with id
"extra2/<name>", so dohmh_profile.py picks it up unchanged. Notes start with FULL,
PARTIAL or DERIVED; see data/notes/dohmh_gaps2.md. Fetch and converter helpers are
reused from dohmh_extra.py.

Run:  .venv/bin/python pipeline/dohmh_extra2.py [name ...]   (fetch missing + register)
      .venv/bin/python pipeline/dohmh_profile.py             (stats + union rebuild)
"""
from __future__ import annotations

import csv
import gzip
import io
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dohmh_extra import GH, MANIFEST, RAW, conv_csv, conv_xlsx, fetch  # noqa: E402

OUT = RAW / "extra2"

# name, source label, url, converter, format tag, curated note
SOURCES = [
    ("gh_omarka_20180503",
     "GitHub omarka/datascience @0306429 (nyc_restaurants/DOHMH_..._Results.tar.xz)",
     f"{GH}/omarka/datascience/03064291c6de5dbf78d42c43e9c3fff9042ca059/nyc_restaurants/"
     "DOHMH_New_York_City_Restaurant_Inspection_Results.tar.xz",
     "tar_member:DOHMH_New_York_City_Restaurant_Inspection_Results.csv", "csv", "FULL"),
    ("gh_vaibhavdiyora88_20180717",
     "GitHub vaibhavdiyora88/an_inspection_of_restaurants_in_NYC @d8af46f (zip member 'NYC restaurants.csv')",
     f"{GH}/vaibhavdiyora88/an_inspection_of_restaurants_in_NYC/d8af46f15e341933aadfdabc741afba744a13b6b/"
     "CSV%20files-Zipcodes%2C%20NYC%20restaurants%2C%20Final%20dataset.zip",
     "zip_member:NYC restaurants.csv", "csv", "FULL (Socrata API field names)"),
    ("gh_tidytuesday_20181208",
     "GitHub rfordatascience/tidytuesday @362fa86 (data/2018/2018-12-11/nyc_restaurants.csv)",
     f"{GH}/rfordatascience/tidytuesday/362fa86c328797428736f05c22af5eca3a27b731/data/2018/2018-12-11/nyc_restaurants.csv",
     "add_rec:2018-12-08", "csv",
     "PARTIAL: random sample of 300,000 rows (sample_n) of the full pull; max insp 2018-12-07, "
     "no record date in source, set to 2018-12-08 (approx); absence != closed"),
    ("gh_css459_20190313",
     "GitHub css459/restaurant-closure-prediction @6c53483 (data.zip member DOHMH_..._Results.csv)",
     f"{GH}/css459/restaurant-closure-prediction/6c534831e0c434232c8047580d6f39035b711c23/data.zip",
     "zip_member:DOHMH_New_York_City_Restaurant_Inspection_Results.csv", "csv", "FULL"),
    ("gh_robblatt_20190604",
     "GitHub robblatt/Restaurant-Hypothesis-Testing @37fc308 (health inspection.csv)",
     f"{GH}/robblatt/Restaurant-Hypothesis-Testing/37fc30821ac384c0be762b41d5c9204c8ebaefee/health%20inspection.csv",
     "add_rec:2019-06-04", "csv",
     "PARTIAL: only inspections dated 2017-06-02..2019-06-03 (pandas filter, index column kept); "
     "no record date in source, set to 2019-06-04 (approx); absence != closed"),
    ("gh_jieyingcai_20211214",
     "GitHub JieyingCai/final-project-restaurant @35648e0 (DOHMH_..._Results.csv, truncated)",
     f"{GH}/JieyingCai/final-project-restaurant/35648e09c73a7006825811f77c93ddc158b60b98/"
     "DOHMH_New_York_City_Restaurant_Inspection_Results.csv",
     "truncated_csv", "csv",
     "PARTIAL: committed file is cut off at exactly 62 MiB (151k of ~330k rows, export row order); "
     "incomplete last row dropped; absence != closed"),
    ("gh_tzstatsads_20220213",
     "GitHub TZstatsADS/spring-2022-project2-group-11 @26a62fa (data/New_York_City_Restaurant_Inspection_Results.xlsx)",
     f"{GH}/TZstatsADS/spring-2022-project2-group-11/26a62faefc88c0d2b29de28169aa3bcb995f0aa3/data/"
     "New_York_City_Restaurant_Inspection_Results.xlsx",
     "xlsx", "csv", "FULL (Excel export; serial dates converted)"),
    ("gh_tzstatsads_20230221",
     "GitHub TZstatsADS/ads-spring2023-project2-group1 @77123a7 (data/DOHMH_..._Results.csv)",
     f"{GH}/TZstatsADS/ads-spring2023-project2-group1/77123a7e21147549b063e782d841df6e03105734/data/"
     "DOHMH_New_York_City_Restaurant_Inspection_Results.csv",
     "csv", "csv", "FULL"),
]


def conv_zip_member(src: Path, dest: Path, member: str) -> None:
    with zipfile.ZipFile(src) as z:
        names = [n for n in z.namelist() if Path(n).name == member and not n.startswith("__MACOSX")]
        if len(names) != 1:
            raise ValueError(f"expected one member named {member!r}, got {names}")
        with z.open(names[0]) as fi, gzip.open(dest, "wb") as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)


def conv_tar_member(src: Path, dest: Path, member: str) -> None:
    import tarfile
    with tarfile.open(src) as t:
        names = [m for m in t.getmembers() if m.isfile() and Path(m.name).name == member]
        if len(names) != 1:
            raise ValueError(f"expected one member named {member!r}, got {[m.name for m in names]}")
        with t.extractfile(names[0]) as fi, gzip.open(dest, "wb") as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)


def conv_truncated_csv(src: Path, dest: Path) -> None:
    """Keep only complete rows of a CSV whose tail was cut off mid-row."""
    data = src.read_bytes()
    keep = data[: data.rfind(b"\n") + 1]
    rows = list(csv.reader(io.StringIO(keep.decode("utf-8"), newline="")))
    width = len(rows[0])
    bad = sum(len(r) != width for r in rows)
    if bad:
        raise ValueError(f"{bad} rows with a wrong field count after trimming the tail")
    print(f"  dropped {len(data) - len(keep)} trailing bytes; kept {len(rows) - 1} rows")
    with gzip.open(dest, "wb") as fo:
        fo.write(keep)


def conv_add_rec(src: Path, dest: Path, rec: str) -> None:
    """Copy a CSV that has no record-date column, appending RECORD DATE = rec (approximate pull date)."""
    with src.open(newline="", encoding="utf-8") as fi, gzip.open(dest, "wt", newline="", encoding="utf-8") as fo:
        r, w = csv.reader(fi), csv.writer(fo, quoting=csv.QUOTE_ALL)
        header = next(r)
        if any(h.strip().lower().replace("_", " ") == "record date" for h in header):
            raise ValueError("source already has a record date column")
        w.writerow(header + ["RECORD DATE"])
        n = 0
        for row in r:
            if len(row) != len(header):
                raise ValueError(f"row {n + 2}: {len(row)} fields, header has {len(header)}")
            w.writerow(row + [rec])
            n += 1


def convert(conv: str, src: Path, dest: Path) -> None:
    kind, _, arg = conv.partition(":")
    if kind == "zip_member":
        conv_zip_member(src, dest, arg)
    elif kind == "tar_member":
        conv_tar_member(src, dest, arg)
    elif kind == "truncated_csv":
        conv_truncated_csv(src, dest)
    elif kind == "add_rec":
        conv_add_rec(src, dest, arg)
    elif kind == "xlsx":
        conv_xlsx([src], dest)
    elif kind == "csv":
        conv_csv([src], dest)
    else:
        raise ValueError(f"unknown converter {conv}")


def register() -> None:
    with MANIFEST.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())
    have = {r["id"] for r in rows}
    added = 0
    for name, label, url, conv, fmt, note in SOURCES:
        mid = f"extra2/{name}"
        if mid in have or not (OUT / f"{name}.csv.gz").exists():
            continue
        rows.append({**{f: "" for f in fields}, "id": mid, "source": label, "kind": "http",
                     "url": url, "format": fmt, "notes": note})
        added += 1
    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"manifest: {added} rows added")


def main(only: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, label, url, conv, fmt, note in SOURCES:
        dest = OUT / f"{name}.csv.gz"
        if (only and name not in only) or dest.exists():
            continue
        print(f"{name}: fetching")
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / ("src" + Path(url.split("?")[0]).suffix)
            fetch(url, src)
            tmp = dest.with_suffix(".tmp")
            convert(conv, src, tmp)
            tmp.rename(dest)
        print(f"  wrote {dest.name} ({dest.stat().st_size:,} bytes)")
    register()


if __name__ == "__main__":
    main(sys.argv[1:])
