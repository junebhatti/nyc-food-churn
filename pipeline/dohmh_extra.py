"""Fetch extra DOHMH copies that fill the 2014-08..2015-09 and 2017-08..2018-07 gaps.

These come from GitHub repos' git history (blobs at old commit SHAs, including
Git LFS objects) and from R data files. Several are derived or partial; see
data/notes/dohmh_gaps.md. Each copy is written as data/raw/dohmh/extra/<name>.csv.gz
and registered in manifest.csv with id "extra/<name>", so dohmh_profile.py picks it
up unchanged (it reads RAW / f"{id}.csv.gz").

Run:  .venv/bin/python pipeline/dohmh_extra.py           (fetch missing + register)
      .venv/bin/python pipeline/dohmh_profile.py         (stats + union rebuild)
The .rda/.RData sources use the pure-python `rdata` package (installed in .venv).
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import sqlite3
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/dohmh"
OUT = RAW / "extra"
MANIFEST = RAW / "manifest.csv"
UA = {"User-Agent": "nyc-food-churn research (personal project; polite sequential fetch)"}
GH = "https://raw.githubusercontent.com"
LFS = "https://media.githubusercontent.com/media"

# name, source label, url(s), converter, format tag, curated note
SOURCES = [
    ("gh_tzstatsads_20180208", "GitHub TZstatsADS/Spring2018-Project2-Group3 @e3b2d30 (data/DOHMH_..._Results.xlsx)",
     [f"{GH}/TZstatsADS/Spring2018-Project2-Group3/e3b2d30710b14a6b4433ebe5a8b749e187a58032/data/"
      "DOHMH_New_York_City_Restaurant_Inspection_Results.xlsx"],
     "xlsx", "csv", "FULL (Excel export; serial dates converted)"),
    ("gh_residentmario_20160927", "GitHub ResidentMario/nyc-restaurant-trends @8404b6b (data/inspections_flattened_initial.csv)",
     [f"{GH}/ResidentMario/nyc-restaurant-trends/8404b6bddf6331f41e9fed6a362a94896a5ca658/data/inspections_flattened_initial.csv"],
     "flattened", "csv",
     "DERIVED: one row per CAMIS (all 26,064 of the pull) with initial + latest inspection; "
     "expanded to <=2 rows per CAMIS; presence evidence only"),
    ("gh_hmason_20130906", "GitHub hmason/datastorytelling @a6c4c14 (Lesson1_restaurants/data/WebExtract.txt)",
     [f"{GH}/hmason/datastorytelling/a6c4c1426f1fa279bc2415f76f2b324ddab4e263/Lesson1_restaurants/data/WebExtract.txt"],
     "webextract_txt", "webextract", "FULL WebExtract, cp1252 transcoded to UTF-8"),
    ("gh_uncamy_20131121", "GitHub uncamy/foodGrades @c83e566 (data/original_data/WebExtract.txt)",
     [f"{GH}/uncamy/foodGrades/c83e566f45ec276ab478b555ef0ab5bc5c00df1b/data/original_data/WebExtract.txt"],
     "webextract_txt", "webextract", "FULL WebExtract, cp1252 transcoded to UTF-8"),
    ("gh_munk_20140213", "GitHub munk/Python4 @296b2fe (data/WebExtract.txt)",
     [f"{GH}/munk/Python4/296b2fe7e264d40142fbfb6898c27cfd04a31952/data/WebExtract.txt"],
     "webextract_txt", "webextract", "FULL WebExtract, cp1252 transcoded to UTF-8"),
    ("lehman_gqhi_20130329", "CUNY Lehman Socrata mirror bronx.lehman.cuny.edu gqhi-7359 (All NYC Restaurant Locations and inspection results)",
     ["https://bronx.lehman.cuny.edu/api/views/gqhi-7359/rows.csv?accessType=DOWNLOAD"], "csv_rec:2013-03-29", "webextract",
     "DERIVED: one row (latest inspection) per CAMIS, all NYC; uploaded 2013-04-04, max insp 2013-03-28; "
     "RECORDDATE was Excel-mangled, set to 2013-03-29; presence evidence only"),
    ("lehman_ptqi_20121129", "CUNY Lehman Socrata mirror bronx.lehman.cuny.edu ptqi-husz (Bronx DOHMH Restaurant Inspections November 2012)",
     ["https://bronx.lehman.cuny.edu/api/views/ptqi-husz/rows.csv?accessType=DOWNLOAD"], "csv_rec:2012-11-29", "webextract",
     "PARTIAL: Bronx only, full history; max insp 2012-11-28; RECORDDATE Excel-mangled, set to 2012-11-29"),
    ("lehman_mt6q_20150705", "CUNY Lehman Socrata mirror bronx.lehman.cuny.edu mt6q-sf39 (Bronx Restaurant Locations and Recent DOHMH Inspections)",
     ["https://bronx.lehman.cuny.edu/api/views/mt6q-sf39/rows.csv?accessType=DOWNLOAD"], "csv", "csv",
     "PARTIAL: Bronx only, inspections 2015-01-02..2015-07-02 only"),
    ("gh_tzstatsads_20161007", "GitHub TZstatsADS/Fall2016-Proj2-grp12 @f946ee0 (output/restaurant_uniques_source.csv)",
     [f"{GH}/TZstatsADS/Fall2016-Proj2-grp12/f946ee020ea6227c8096f21932153cb85298f385/output/restaurant_uniques_source.csv"],
     "camis_list", "csv",
     "DERIVED: one row per CAMIS (no inspection dates) from a pull made on or before the 2016-10-07 commit; "
     "RECORD DATE set to 2016-10-07; presence evidence only"),
    ("wb_v3_20260605", "Wayback Machine (Socrata v3 export export.xlsx)",
     ["https://web.archive.org/web/20260605151618id_/http://data.cityofnewyork.us/api/v3/views/43nn-pn8j/export.xlsx"],
     "xlsx", "csv", "FULL; v3 export endpoint captured 20260605151618"),
    ("wb_v3_20260807", "Wayback Machine (Socrata v3 export export.csv)",
     ["https://web.archive.org/web/20260807192852id_/http://data.cityofnewyork.us/api/v3/views/43nn-pn8j/export.csv?accessType=DOWNLOAD"],
     "csv", "csv", "FULL; v3 export endpoint captured 20260807192852"),
    ("wb_v3_20260925", "Wayback Machine (Socrata v3 export export.xlsx)",
     ["https://web.archive.org/web/20260925133000id_/http://data.cityofnewyork.us/api/v3/views/43nn-pn8j/export.xlsx"],
     "xlsx", "csv", "FULL; v3 export endpoint captured 20260925133000"),
    ("gh_ryankanno_20120706", "GitHub ryankanno/archive-nyc-restaurant-inspections-api @5aa8dd2 (data/dohmh_restaurant-inspections_002.zip)",
     [f"{GH}/ryankanno/archive-nyc-restaurant-inspections-api/5aa8dd290487536e2263e6d23bf893dcaea9f053/data/dohmh_restaurant-inspections_002.zip"],
     "zip_webextract", "webextract", "FULL WebExtract (BigApps zip), cp1252 transcoded to UTF-8"),
    ("gh_ryankanno_20121019", "GitHub ryankanno/archive-nyc-restaurant-inspections-api @0600762 (data/dohmh_restaurant-inspections_002.zip)",
     [f"{GH}/ryankanno/archive-nyc-restaurant-inspections-api/0600762b64927b6d725606ad1975caa4364a8b89/data/dohmh_restaurant-inspections_002.zip"],
     "zip_webextract", "webextract", "FULL WebExtract (BigApps zip), cp1252 transcoded to UTF-8"),
    ("gh_mrsnickers_20140320", "GitHub MrSnickers/Restaurant_cleaner @3d345f2 (RestaurantCleaner/public/data/Inspections.txt)",
     [f"{GH}/MrSnickers/Restaurant_cleaner/3d345f213b5969ea36c0c713771cfe790d72cb86/RestaurantCleaner/public/data/Inspections.txt"],
     "webextract_txt", "webextract", "FULL WebExtract, cp1252 transcoded to UTF-8"),
    ("gh_datacomputing_20141009", "GitHub DataComputing/RestaurantsNYC @f7341d7 (data/Violations.rda)",
     [f"{GH}/DataComputing/RestaurantsNYC/f7341d73d450540fdb1f08612dfeca861665e6e9/data/Violations.rda"],
     "rda_violations", "webextract",
     "FULL WebExtract pull (boro/cuisine coded); dates were POSIXct, converted to UTC dates"),
    ("gh_akkaluzny_20141102", "GitHub akkaluzny/nyc_health @09b15ac (data/inspectionData.csv + restaurantData.csv)",
     [f"{GH}/akkaluzny/nyc_health/09b15ac901932e0820951cbca2543c9e5aa90367/data/inspectionData.csv",
      f"{GH}/akkaluzny/nyc_health/09b15ac901932e0820951cbca2543c9e5aa90367/data/restaurantData.csv"],
     "akkaluzny", "csv",
     "DERIVED: one row per inspection (no violation rows); all CAMIS of the pull; attributes joined from restaurantData"),
    ("gh_vsm1013_20150212", "GitHub vsm1013/NYC-Restaurants-Exploratory-Data-Analysis @540b5fd (HW#2 csv)",
     [f"{GH}/vsm1013/NYC-Restaurants-Exploratory-Data-Analysis/540b5fd6986d713a03994dc4420a77f007522ac5/"
      "NYC_Restaurants%20(HW%232%20Data).csv"],
     "csv", "csv",
     "PARTIAL: only inspections dated 2014-11-01..2015-01-31 (course subset); absence != closed"),
    ("gh_bethannezink_20150301", "GitHub bethannezink/food-grader @8e1d3f2 (db/development.sqlite)",
     [f"{GH}/bethannezink/food-grader/8e1d3f29b28210ff6d6756e28a044247d570891d/db/development.sqlite"],
     "sqlite_bethannezink", "csv",
     "FULL pull, max insp 2015-02-27, no CAMIS/record date in source: CAMIS matched to other copies; "
     "unmatched restaurants get CAMIS 'X<rowid>'; RECORD DATE set to 2015-03-01 (approx)"),
    ("gh_compjour_20150802", "GitHub compjour/tutorial-data-stash @84d47a1 (data-holding/nyc_restaurants/downloaded/*.csv)",
     ["tree:compjour/tutorial-data-stash/84d47a15df65c90f40b69dabf9a0c1110eface99/data-holding/nyc_restaurants/downloaded"],
     "concat_csv", "csv", "FULL pull split by inspection month (58 files) and concatenated here"),
    ("gh_ldgarber_20170908", "GitHub ldgarber/nyc-restaurant-inspections @db999b5 (LFS db/raw_inspection_data.csv)",
     [f"{LFS}/ldgarber/nyc-restaurant-inspections/db999b5acf5747a53e2fcab1bb9acd2b35370ea8/db/raw_inspection_data.csv"],
     "csv", "csv", "FULL"),
    ("gh_p8105_20171019", "GitHub lynetteyuepan/p8105_hw6_yp2463 @1913d9a (Columbia P8105 course copy; = p8105.datasets rest_inspec)",
     [f"{GH}/lynetteyuepan/p8105_hw6_yp2463/1913d9a17c4ae019411393b51d0d7a2ac05cc13f/"
      "DOHMH_New_York_City_Restaurant_Inspection_Results.csv.gz"],
     "gz", "csv", "FULL; Socrata API field names, ISO dates"),
    ("gh_miguel75an_20180301", "GitHub Miguel75An/ExperimentingWithData @85169af (nyc_restaurants.csv)",
     [f"{GH}/Miguel75An/ExperimentingWithData/85169afbd476d76b42d4e3986f9631ffe83228fc/nyc_restaurants.csv"],
     "csv", "csv",
     "PARTIAL: ~30% of rows (115k of ~380k) but 23.7k CAMIS; absence != closed"),
    ("gh_ccw2145_20180406", "GitHub ccw2145/edav_project @a4cbb80 (data/data.RData object 'data')",
     [f"{GH}/ccw2145/edav_project/a4cbb80ce96ceffb458b3d807564a348998f5050/data/data.RData"],
     "rdata_ccw2145", "csv", "FULL (R data.frame of the raw CSV)"),
    ("gh_smach_20170605", "GitHub smach/R4JournalismBook (nycinspections/nycdata.zip)",
     [f"{GH}/smach/R4JournalismBook/HEAD/nycinspections/nycdata.zip"],
     "zip", "csv", "FULL"),
]


def fetch(url: str, dest: Path) -> None:
    for attempt in range(4):
        try:
            with requests.get(url, stream=True, timeout=(30, 300), headers=UA) as r:
                r.raise_for_status()
                with dest.open("wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
            if dest.stat().st_size < 1000 and dest.read_bytes().startswith(b"version https://git-lfs"):
                raise ValueError(f"{url} is a Git LFS pointer, not data")
            time.sleep(3)
            return
        except (requests.RequestException, ValueError) as e:
            print(f"  attempt {attempt + 1} failed for {url}: {e}", file=sys.stderr)
            if attempt == 3:
                raise
            time.sleep(10 * (attempt + 1))


def write_rows(dest: Path, header: list[str], rows) -> None:
    with gzip.open(dest, "wt", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def read_r(path: Path) -> dict:
    try:
        import rdata
    except ImportError as e:
        raise SystemExit("this source needs the `rdata` package: .venv/bin/pip install rdata") from e
    parsed = rdata.parser.parse_file(path)
    return rdata.conversion.convert(parsed, default_encoding="latin1", force_default_encoding=True)


def epoch_date(v) -> str:
    if v is None or v != v:  # None or NaN
        return ""
    return datetime.fromtimestamp(float(v), tz=timezone.utc).strftime("%Y-%m-%d")


def conv_rda_violations(src: list[Path], dest: Path) -> None:
    df = read_r(src[0])["Violations"]
    for c in ("INSPDATE", "GRADEDATE", "RECORDDATE"):
        df[c] = df[c].map(epoch_date)
    df["PHONE"] = df["PHONE"].astype(str).replace("2147483647", "")  # R int overflow sentinel
    with gzip.open(dest, "wt", newline="", encoding="utf-8") as fh:
        df.to_csv(fh, index=False)


def conv_rdata_ccw2145(src: list[Path], dest: Path) -> None:
    df = read_r(src[0])["data"]
    df.columns = [c.replace(".", " ") for c in df.columns]
    with gzip.open(dest, "wt", newline="", encoding="utf-8") as fh:
        df.to_csv(fh, index=False)


def conv_akkaluzny(src: list[Path], dest: Path) -> None:
    with src[1].open(newline="", encoding="utf-8") as fh:
        rest = {r["CAMIS"]: r for r in csv.DictReader(fh)}
    attrs = ["DBA", "BORO", "BUILDING", "STREET", "ZIPCODE", "PHONE", "CUISINE.DESCRIPTION"]
    insp = ["INSPECTION.DATE", "ACTION", "SCORE", "GRADE", "GRADE.DATE", "RECORD.DATE", "INSPECTION.TYPE"]
    missing = 0

    def rows():
        nonlocal missing
        with src[0].open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                a = rest.get(r["CAMIS"])
                if a is None:
                    missing += 1
                    a = {}
                yield [r["CAMIS"]] + [(a.get(k) or "").strip() for k in attrs] + \
                      [("" if r[k] == "NA" else r[k]) for k in insp]
    write_rows(dest, ["CAMIS"] + attrs + insp, rows())
    if missing:
        print(f"  WARNING: {missing} inspection rows had no restaurantData match", file=sys.stderr)


def conv_csv(src: list[Path], dest: Path) -> None:
    with src[0].open("rb") as fi, gzip.open(dest, "wb") as fo:
        while chunk := fi.read(1 << 20):
            fo.write(chunk)


def expand_tree(url: str) -> list[str]:
    """'tree:owner/repo/sha/dir' -> raw URLs of every .csv in that directory at that sha."""
    owner, repo, sha, d = url[5:].split("/", 3)
    r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/git/trees/{sha}:{d}", headers=UA, timeout=60)
    r.raise_for_status()
    j = r.json()
    if j.get("truncated"):
        raise ValueError(f"tree listing truncated for {url}")
    return [f"{GH}/{owner}/{repo}/{sha}/{d}/{t['path']}" for t in j["tree"] if t["path"].endswith(".csv")]


def conv_concat_csv(src: list[Path], dest: Path) -> None:
    header = None
    with gzip.open(dest, "wt", newline="", encoding="utf-8") as fo:
        for p in sorted(src):
            with p.open(newline="", encoding="utf-8") as fi:
                h = fi.readline()
                if header is None:
                    header = h
                    fo.write(h)
                elif h != header:
                    raise ValueError(f"{p.name}: header differs from first file")
                while chunk := fi.read(1 << 20):
                    fo.write(chunk)


def _transcode(fi, dest: Path) -> None:
    """cp1252 bytes stream -> UTF-8 gzip (old DOH WebExtract files are cp1252)."""
    import codecs
    rd = codecs.getreader("cp1252")(fi, errors="replace")
    with gzip.open(dest, "wt", encoding="utf-8", newline="") as fo:
        while chunk := rd.read(1 << 20):
            fo.write(chunk)


def conv_webextract_txt(src: list[Path], dest: Path) -> None:
    with src[0].open("rb") as fi:
        _transcode(fi, dest)


def conv_zip_webextract(src: list[Path], dest: Path) -> None:
    with zipfile.ZipFile(src[0]) as z, z.open("WebExtract.txt") as fi:
        _transcode(fi, dest)


def conv_xlsx(src: list[Path], dest: Path) -> None:
    """Stream the first sheet of an .xlsx to CSV (no openpyxl dependency)."""
    from xml.etree.ElementTree import iterparse
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(src[0]) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            with z.open("xl/sharedStrings.xml") as fh:
                for _, el in iterparse(fh):
                    if el.tag == ns + "si":
                        shared.append("".join(t.text or "" for t in el.iter(ns + "t")))
                        el.clear()
        sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]

        def col(ref: str) -> int:
            n = 0
            for ch in ref:
                if ch.isalpha():
                    n = n * 26 + ord(ch.upper()) - 64
                else:
                    break
            return n - 1

        def rows():
            with z.open(sheet) as fh:
                for _, el in iterparse(fh):
                    if el.tag != ns + "row":
                        continue
                    vals = {}
                    for c in el.iter(ns + "c"):
                        t, v = c.get("t"), c.find(ns + "v")
                        if t == "s" and v is not None:
                            x = shared[int(v.text)]
                        elif t == "inlineStr":
                            x = "".join(e.text or "" for e in c.iter(ns + "t"))
                        else:
                            x = v.text if v is not None else ""
                        vals[col(c.get("r"))] = x
                    el.clear()
                    if vals:
                        yield [vals.get(i, "") for i in range(max(vals) + 1)]
        it = rows()
        header = next(it)
        width = len(header)
        dcols = [i for i, h in enumerate(header) if "DATE" in h.upper()]
        base = datetime(1899, 12, 30)

        def fix(r):
            r = r[:width] + [""] * (width - len(r))
            for i in dcols:  # Excel serial day numbers -> ISO dates
                if re.fullmatch(r"\d+(\.\d+)?", r[i]):
                    r[i] = (base + timedelta(days=float(r[i]))).strftime("%Y-%m-%d")
            return r
        write_rows(dest, header, (fix(r) for r in it))


def conv_camis_list(src: list[Path], dest: Path) -> None:
    """CAMIS,DBA,CUISINE.DESCRIPTION,full.address -> presence-only rows (empty INSPECTION DATE)."""
    with src[0].open(newline="", encoding="utf-8") as fh:
        rows = [[r["CAMIS"], r["DBA"], r["full.address"], r["CUISINE.DESCRIPTION"], "", "2016-10-07"]
                for r in csv.DictReader(fh)]
    write_rows(dest, ["CAMIS", "DBA", "STREET", "CUISINE DESCRIPTION", "INSPECTION DATE", "RECORD DATE"], rows)


def conv_csv_rec(src: list[Path], dest: Path, rec: str) -> None:
    """Copy a CSV, overwriting its (garbled) record-date column with `rec`."""
    with src[0].open(newline="", encoding="utf-8") as fh:
        r = csv.reader(fh)
        header = next(r)
        i = next(k for k, h in enumerate(header) if re.sub(r"[^a-z]", "", h.lower()) == "recorddate")
        write_rows(dest, header, (row[:i] + [rec] + row[i + 1:] for row in r))


def conv_flattened(src: list[Path], dest: Path) -> None:
    """ResidentMario per-CAMIS rows -> one row per (CAMIS, initial/latest inspection date)."""
    attrs = ["DBA", "BORO", "BUILDING", "STREET", "ZIPCODE", "PHONE", "CUISINE DESCRIPTION"]

    def rows():
        with src[0].open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                a = [re.sub(r"\.0$", "", r[f"DOHMH {k}"]) for k in attrs]
                rec = r["DOHMH RECORD DATE"]
                yield [r["CAMIS"], *a, r["DOHMH INITIAL INSPECTION DATE"], r["DOHMH INITIAL INSPECTION TYPE"], rec]
                if r["DOHMH LATEST INSPECTION DATE"] != r["DOHMH INITIAL INSPECTION DATE"]:
                    yield [r["CAMIS"], *a, r["DOHMH LATEST INSPECTION DATE"], "", rec]
    write_rows(dest, ["CAMIS", *attrs, "INSPECTION DATE", "INSPECTION TYPE", "RECORD DATE"], rows())


def conv_gz(src: list[Path], dest: Path) -> None:
    with gzip.open(src[0], "rb") as fi:  # validates it is gzip
        fi.read(1)
    dest.write_bytes(src[0].read_bytes())


def conv_zip(src: list[Path], dest: Path) -> None:
    with zipfile.ZipFile(src[0]) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one csv in zip, got {names}")
        with z.open(names[0]) as fi, gzip.open(dest, "wb") as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)


def _n(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def conv_sqlite_bethannezink(src: list[Path], dest: Path) -> None:
    """Restaurant ids follow the source CSV's CAMIS order. Match each restaurant to a
    CAMIS seen in the neighbouring copies by phone/name/zip, scored by overlap of
    inspection dates, then require the matches to be monotonic in rowid."""
    import duckdb
    con = sqlite3.connect(src[0])
    rest = con.execute("SELECT id, name, address, phone_number, restaurant_style, borough "
                       "FROM restaurants ORDER BY id").fetchall()
    insp = con.execute("SELECT restaurant_id, date, grade, score, violation_code FROM inspections "
                       "ORDER BY id").fetchall()
    con.close()
    dates: dict[int, set] = {}
    for rid, d, *_ in insp:
        if d and d > "1901":
            dates.setdefault(rid, set()).add(d[:10])

    near = [p for p in sorted(OUT.glob("*.csv.gz")) if re.search(r"_(2014|2015)\d{4}\.csv\.gz$", p.name)
            and "bethannezink" not in p.name]
    near += [RAW / "gh_spkal_20140828.csv.gz", RAW / "wayback_20150908_csv.csv.gz"]
    d = duckdb.connect()
    opts = "all_varchar=true, header=true, sample_size=-1, strict_mode=false"
    parts = []
    for p in near:
        cols = {re.sub(r"[^a-z]", "", c.lower()): c for c in
                d.execute(f"SELECT * FROM read_csv('{p}', {opts}) LIMIT 0").fetchdf().columns}
        idate = cols.get("inspectiondate") or cols.get("inspdate")
        parts.append(f"""SELECT "{cols['camis']}" camis, "{cols['dba']}" dba, "{cols['phone']}" phone,
            "{cols['zipcode']}" zipcode, "{cols['building']}" building,
            coalesce(try_strptime("{idate}", '%m/%d/%Y')::date, try_strptime(left("{idate}",10), '%Y-%m-%d')::date)::varchar d
            FROM read_csv('{p}', {opts})""")
    ref = d.execute(" UNION ALL ".join(parts)).fetchall()
    by_phone, by_name, cam_dates, cam_keys = {}, {}, {}, {}
    for camis, dba, phone, zipc, bldg, dt in ref:
        if not camis:
            continue
        cam_dates.setdefault(camis, set()).add(dt)
        ph = re.sub(r"\D", "", phone or "")
        cam_keys.setdefault(camis, set()).update({("n", _n(dba)), ("p", ph)})
        if len(ph) == 10:
            by_phone.setdefault(ph, set()).add(camis)
        by_name.setdefault((_n(dba), (zipc or "")[:5]), set()).add(camis)

    # Score every (restaurant, candidate CAMIS) pair, then assign greedily one-to-one,
    # since one site (same name+phone) often holds several CAMIS (e.g. club kitchens).
    pairs = []
    for rid, name, addr, phone, style, boro in rest:
        z = re.search(r"(\d{5})\s*$", addr or "")
        by_ph = by_phone.get(re.sub(r"\D", "", phone or ""), set())
        by_nm = by_name.get((_n(name), z.group(1) if z else ""), set())
        mine = dates.get(rid, set())
        for c in by_ph | by_nm:
            theirs = cam_dates.get(c, set()) - {None}
            shared = len(mine & theirs)
            # inspected: need >=1 shared inspection date; never inspected: need phone AND name+zip
            if (mine and shared) or (not mine and c in by_ph and c in by_nm):
                jac = shared / len(mine | theirs) if mine else 0.0
                pairs.append((shared + jac + 0.5 * (c in by_nm) + 0.25 * (c in by_ph), rid, c))
    match: dict[int, str] = {}
    taken: set[str] = set()
    for score, rid, c in sorted(pairs, reverse=True):
        if rid not in match and c not in taken:
            match[rid] = c
            taken.add(c)
    # Second pass by position: an unmatched restaurant's CAMIS lies strictly between its
    # matched neighbours' CAMIS. Take the best free CAMIS in that range scored by shared
    # inspection dates (2 each), same name (1.5), same phone (1); need >= 2 and a unique best.
    import bisect
    pool = sorted(int(c) for c in cam_dates if c.isdigit())
    ids = [r[0] for r in rest]
    info = {r[0]: r for r in rest}
    for i, rid in enumerate(ids):
        if rid in match:
            continue
        lo = next((int(match[x]) for x in reversed(ids[:i]) if x in match), 0)
        hi = next((int(match[x]) for x in ids[i + 1:] if x in match), 10 ** 9)
        _, name, addr, phone, *_ = info[rid]
        keys = {("n", _n(name)), ("p", re.sub(r"\D", "", phone or ""))}
        scored = []
        for c in pool[bisect.bisect_right(pool, lo):bisect.bisect_left(pool, hi)]:
            c = str(c)
            if c in taken:
                continue
            k = cam_keys[c] & keys
            s = 2 * len(dates.get(rid, set()) & cam_dates[c]) + 1.5 * (("n", _n(name)) in k) + 1.0 * any(
                t == "p" and v for t, v in k)
            scored.append((s, c))
        scored.sort(reverse=True)
        if scored and scored[0][0] >= 2 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
            match[rid] = scored[0][1]
            taken.add(scored[0][1])
    # drop matches that break CAMIS order relative to both neighbours
    ids = sorted(match)
    bad = {ids[i] for i in range(1, len(ids) - 1)
           if not (int(match[ids[i - 1]]) <= int(match[ids[i]]) or int(match[ids[i]]) <= int(match[ids[i + 1]]))}
    for rid in bad:
        del match[rid]
    print(f"  matched {len(match)}/{len(rest)} restaurants to CAMIS ({len(bad)} dropped as out of order)")

    def rows():
        for rid, dt, grade, score, viol in insp:
            _, name, addr, phone, style, boro = info[rid]
            z = re.search(r"(\d{5})\s*$", addr or "")
            m = re.match(r"\s*(\S+)\s+(.*?)\s+(?:Manhattan|Brooklyn|Bronx|Queens|Staten Island),", addr or "", re.I)
            yield [match.get(rid, f"X{rid}"), name, boro, m.group(1) if m else "", m.group(2) if m else addr,
                   z.group(1) if z else "", phone, style, (dt or "")[:10], viol or "", score if score is not None else "",
                   grade or "", "2015-03-01"]
    write_rows(dest, ["CAMIS", "DBA", "BORO", "BUILDING", "STREET", "ZIPCODE", "PHONE", "CUISINE DESCRIPTION",
                      "INSPECTION DATE", "VIOLATION CODE", "SCORE", "GRADE", "RECORD DATE"], rows())


CONVERT = {"rda_violations": conv_rda_violations, "rdata_ccw2145": conv_rdata_ccw2145,
           "akkaluzny": conv_akkaluzny, "csv": conv_csv, "gz": conv_gz, "zip": conv_zip,
           "sqlite_bethannezink": conv_sqlite_bethannezink, "concat_csv": conv_concat_csv,
           "webextract_txt": conv_webextract_txt, "zip_webextract": conv_zip_webextract,
           "xlsx": conv_xlsx, "camis_list": conv_camis_list,
           "flattened": conv_flattened}


def register() -> None:
    with MANIFEST.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys())
    have = {r["id"] for r in rows}
    added = 0
    for name, label, urls, conv, fmt, note in SOURCES:
        mid = f"extra/{name}"
        if mid in have or not (OUT / f"{name}.csv.gz").exists():
            continue
        rows.append({**{f: "" for f in fields}, "id": mid, "source": label, "kind": "http",
                     "url": " ".join(urls), "format": fmt, "notes": note})
        added += 1
    with MANIFEST.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"manifest: {added} rows added")


def main(only: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, label, urls, conv, fmt, note in SOURCES:
        dest = OUT / f"{name}.csv.gz"
        if (only and name not in only) or dest.exists():
            continue
        urls = [x for u in urls for x in (expand_tree(u) if u.startswith("tree:") else [u])]
        print(f"{name}: fetching {len(urls)} file(s)")
        with tempfile.TemporaryDirectory() as td:
            src = []
            for i, u in enumerate(urls):
                p = Path(td) / f"src{i:03d}{Path(u.split('?')[0]).suffix}"
                fetch(u, p)
                src.append(p)
            tmp = dest.with_suffix(".tmp")
            if conv.startswith("csv_rec:"):
                conv_csv_rec(src, tmp, conv.split(":", 1)[1])
            else:
                CONVERT[conv](src, tmp)
            tmp.rename(dest)
        print(f"  wrote {dest.name} ({dest.stat().st_size:,} bytes)")
    register()


if __name__ == "__main__":
    main(sys.argv[1:])
