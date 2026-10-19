"""REBNY Manhattan Retail Report (fall / second-half editions): average ground-floor asking rent
($/sq ft/yr) per corridor, parsed from the "AVERAGE ASKING RENT" table with pdftotext -layout.
2019+ editions present corridors as charts only, so the table parse covers fall 2010-2018
(each fall table also carries the prior fall column). Output: rebny_manhattan_corridor_rents.csv
"""
from __future__ import annotations

import re
import subprocess

import pandas as pd

from gov_common import OUT, get, register_file

PDF_DIR = OUT / "rebny_pdf"
REPORTS = [f"fall-{y}-retail-report" for y in range(2011, 2016)] + \
          [f"fall-{y}-manhattan-retail-report" for y in range(2016, 2023)] + \
          [f"manhattan-retail-report-second-half-{y}" for y in (2023, 2024, 2025)]
VAL = r"(\$[\d,]+|N/A)"
ROW = re.compile(rf"^\s*(?P<name>[A-Za-z0-9].*?)\s{{2,}}{VAL}\s+{VAL}\s+{VAL}\b")


# canonical corridor -> regex over a simplified label (lowercase, ordinals/punctuation stripped)
CORRIDORS = {
    "Madison Ave 57-72 St": r"madison.*57.*72", "Third Ave 60-72 St": r"(third|3) av.*60.*72",
    "E 86 St Lexington-2 Ave": r"^(east |e )?86 st|upper east side|86 :? ?lex",
    "Broadway 72-86 St": r"broadway.*72.*86|upper west side",
    "Columbus Ave 66-79 St": r"columbus", "E 57 St 5 Ave-Park Ave": r"57 st.*(5|fifth).*park",
    "Fifth Ave 42-49 St": r"(fifth|5) av.*42.*49", "Fifth Ave 49-59 St": r"(fifth|5) av.*49.*59",
    "Times Sq Broadway & 7 Ave 42-47 St": r"broadway.*7 av.*42.*47",
    "Fifth Ave 14-23 St": r"(fifth|5) av.*14.*23", "Broadway 14-23 St": r"broadway.*14.*23",
    "W 34 St 5-7 Ave": r"34 st|herald", "14 St 9-10 Ave": r"^(west )?14 st.*9.*10|meatpacking",
    "Broadway Battery Park-Chambers St": r"broadway.*battery|financial district",
    "Broadway Houston-Broome St": r"broadway.*houston.*broome|soho",
    "Bleecker St 7 Ave S-Hudson St": r"blee?c?ker|bleaker",
    "125 St Harlem": r"125",
}


def canonical(label: str) -> str | None:
    s = label.lower().replace("–", "-")
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"\bstreet\b", "st", s)
    s = re.sub(r"\bavenue\b", "av", s)
    s = re.sub(r"\bave\b", "av", s)
    for w, n in (("fifth", "5"), ("seventh", "7"), ("ninth", "9"), ("tenth", "10")):
        s = re.sub(rf"\b{w}\b", n, s)
    s = re.sub(r"[.,:()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    hits = [k for k, rx in CORRIDORS.items() if re.search(rx, s)]
    return hits[0] if len(hits) == 1 else None


def download():
    PDF_DIR.mkdir(exist_ok=True)
    for slug in REPORTS:
        year = re.search(r"20\d\d", slug).group()
        path = PDF_DIR / f"H2_{year}.pdf"
        if path.exists():
            continue
        html = get(f"https://www.rebny.com/reports/{slug}/").text
        m = [u for u in re.findall(r"ctfassets\.net/[^\"#?]*\.pdf", html)
             if not re.search(r"UCBA|Ethics|epa", u)]
        if not m:
            print(f"  {slug}: no PDF link found")
            continue
        path.write_bytes(get("https://assets." + m[0]).content)


def parse(year: int) -> list[dict]:
    txt = subprocess.run(["pdftotext", "-layout", str(PDF_DIR / f"H2_{year}.pdf"), "-"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    # The average-asking-rent table is the first corridor table in every edition (median and
    # min/max tables follow), so keep the first row seen per corridor label.
    rows, seen = [], set()
    for line in txt:
        m = ROW.match(line)
        if not m:
            continue
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        if name in seen or "$" in name or not re.search(r"[A-Za-z]{2}", name):
            continue
        seen.add(name)
        num = lambda v: None if v == "N/A" else float(v.strip("$").replace(",", ""))
        rows.append({"report_year": year, "corridor": name, "year": year,
                     "avg_asking_rent_psf": num(m.group(2))})
        rows.append({"report_year": year, "corridor": name, "year": year - 1,
                     "avg_asking_rent_psf": num(m.group(4))})
    return rows


def run():
    print("== REBNY")
    download()
    rows = []
    for slug in REPORTS:
        y = int(re.search(r"20\d\d", slug).group())
        if (PDF_DIR / f"H2_{y}.pdf").exists():
            r = parse(y)
            print(f"  {y}: {len(r)//2} corridors")
            rows += r
    df = pd.DataFrame(rows).dropna(subset=["avg_asking_rent_psf"])
    df["corridor_label"] = df.pop("corridor")
    df["corridor"] = df["corridor_label"].map(canonical)
    print("  unmatched labels dropped:", sorted(df.loc[df.corridor.isna(), "corridor_label"].unique()))
    df = df.dropna(subset=["corridor"])
    # first table in each report = averages; drop later duplicates of the same corridor
    df = df.drop_duplicates(["report_year", "corridor", "year"], keep="first")
    chk = df.pivot_table(index=["corridor", "year"], columns=df["report_year"] == df["year"],
                         values="avg_asking_rent_psf", aggfunc="first").dropna()
    if len(chk):
        agree = (abs(chk[True] - chk[False]) / chk[True] < 0.02).mean()
        print(f"  QA: own-report value vs next report's prior-fall column agree (<2%): {agree:.0%} of {len(chk)}")
    # prefer the value printed in that year's own report over the next report's "prior fall"
    df["own"] = df["report_year"] == df["year"]
    df = df.sort_values("own", ascending=False).drop_duplicates(["corridor", "year"])
    df = df.drop(columns="own").sort_values(["corridor", "year"])
    out = OUT / "rebny_manhattan_corridor_rents.csv"
    df.to_csv(out, index=False)
    register_file("rebny_manhattan_corridor_rents", out, source="rebny.com retail report PDFs",
                  dataset_id="REBNY Manhattan Retail Report (fall/H2)", rows=len(df),
                  fields=list(df.columns), date_range={"year": [int(df.year.min()), int(df.year.max())]},
                  note="Avg ground-floor asking rent $/sqft/yr, 17 corridors; parsed with pdftotext.")
    print(f"saved {out.name}: {len(df)} rows, years {df.year.min()}-{df.year.max()}, "
          f"{df.corridor.nunique()} corridor labels")


if __name__ == "__main__":
    run()
